import base64
import uuid
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock
from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_clock, get_session_for_current_user
from app.domain.inbox.service import (
    BulkPartialFailureError,
    BulkReassignForbiddenError,
    InboxRow,
    InboxService,
    InvalidSectionError,
    InvalidSectionOrderError,
    ReassignTargetNotActiveError,
)
from app.domain.users.models import User

router = APIRouter(tags=["inbox"])

_SEPARATOR = "\x1f"


class InboxRowResponse(BaseModel):
    post_id: uuid.UUID
    lawsuit_id: uuid.UUID
    task_type_name: str
    scheduled_date: date | None
    scheduled_time: time | None
    deadline_date: date | None
    is_urgent: bool
    is_important: bool
    is_private: bool
    is_read: bool
    is_starred: bool
    created_at: datetime
    parties: list[str]
    assignee_names: list[str]


class InboxPageResponse(BaseModel):
    """Contrato de listagem do CLAUDE.md §6 — keyset por seção (regra 10). O total
    por seção vem do /inbox/counts (regra 8: uma query para as 6), não por página."""

    items: list[InboxRowResponse]
    next_cursor: str | None


class InboxPreferencesResponse(BaseModel):
    section_order: list[str]
    collapsed_sections: list[str]
    page_size: int


class InboxPreferencesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_order: list[str]
    collapsed_sections: list[str] = []


class BulkIdsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    post_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


class BulkFlagRequest(BulkIdsRequest):
    value: bool = True


class BulkReassignRequest(BulkIdsRequest):
    to_user_id: uuid.UUID


def _to_row_response(row: InboxRow) -> InboxRowResponse:
    return InboxRowResponse(
        post_id=row.post_id,
        lawsuit_id=row.lawsuit_id,
        task_type_name=row.task_type_name,
        scheduled_date=row.scheduled_date,
        scheduled_time=row.scheduled_time,
        deadline_date=row.deadline_date,
        is_urgent=row.is_urgent,
        is_important=row.is_important,
        is_private=row.is_private,
        is_read=row.is_read,
        is_starred=row.is_starred,
        created_at=row.created_at,
        parties=row.parties,
        assignee_names=row.assignee_names,
    )


def _encode_cursor(row: InboxRow) -> str:
    raw = f"{row.created_at.isoformat()}{_SEPARATOR}{row.post_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    value, _, id_str = raw.rpartition(_SEPARATOR)
    return datetime.fromisoformat(value), uuid.UUID(id_str)


def _service(session: AsyncSession, user: User) -> InboxService:
    return InboxService(session=session, tenant_id=user.tenant_id)


def _raise_bulk_errors(exc: Exception) -> None:
    if isinstance(exc, BulkPartialFailureError):
        # Regra 6: falha parcial → 409 com os ids problemáticos (a transação inteira
        # desfaz — a sessão da request faz rollback no teardown).
        raise HTTPException(
            status_code=409,
            detail={
                "detail": exc.reason,
                "failed_ids": [str(post_id) for post_id in exc.failed_ids],
            },
        ) from exc
    if isinstance(exc, BulkReassignForbiddenError):
        raise HTTPException(
            status_code=403, detail="Reatribuir em massa exige perfil ADMINISTRADOR."
        ) from exc
    if isinstance(exc, ReassignTargetNotActiveError):
        raise HTTPException(
            status_code=422, detail="O novo responsável precisa ser um usuário ativo do tenant."
        ) from exc
    raise exc


@router.get("/inbox")
async def list_inbox(
    section: str = Query(),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    clock: Clock = Depends(get_clock),
) -> InboxPageResponse:
    service = _service(session, current_user)
    try:
        rows, has_more = await service.list_section(
            current_user,
            section=section,
            cursor=_decode_cursor(cursor) if cursor else None,
            limit=limit,
            today=clock.today(),
        )
    except InvalidSectionError as exc:
        raise HTTPException(status_code=422, detail="Seção desconhecida.") from exc
    return InboxPageResponse(
        items=[_to_row_response(row) for row in rows],
        next_cursor=_encode_cursor(rows[-1]) if has_more and rows else None,
    )


@router.get("/inbox/counts")
async def inbox_counts(
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    clock: Clock = Depends(get_clock),
) -> dict[str, int]:
    service = _service(session, current_user)
    return await service.counts(current_user, clock.today())


@router.get("/inbox/preferences")
async def get_inbox_preferences(
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> InboxPreferencesResponse:
    service = _service(session, current_user)
    order, collapsed, page_size = await service.get_preferences(current_user)
    return InboxPreferencesResponse(
        section_order=order, collapsed_sections=collapsed, page_size=page_size
    )


@router.put("/inbox/preferences")
async def put_inbox_preferences(
    payload: InboxPreferencesRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> InboxPreferencesResponse:
    service = _service(session, current_user)
    try:
        order, collapsed, page_size = await service.update_preferences(
            current_user,
            section_order=payload.section_order,
            collapsed_sections=payload.collapsed_sections,
        )
    except InvalidSectionOrderError as exc:
        raise HTTPException(
            status_code=422, detail="A ordem precisa ser uma permutação das 6 seções."
        ) from exc
    except InvalidSectionError as exc:
        raise HTTPException(status_code=422, detail="Seção desconhecida.") from exc
    return InboxPreferencesResponse(
        section_order=order, collapsed_sections=collapsed, page_size=page_size
    )


@router.post("/posts/bulk/complete")
async def bulk_complete(
    payload: BulkIdsRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> dict[str, int]:
    service = _service(session, current_user)
    try:
        await service.bulk_complete(current_user, payload.post_ids)
    except BulkPartialFailureError as exc:
        _raise_bulk_errors(exc)
    return {"updated": len(payload.post_ids)}


@router.post("/posts/bulk/read")
async def bulk_read(
    payload: BulkFlagRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> dict[str, int]:
    service = _service(session, current_user)
    try:
        await service.bulk_read(current_user, payload.post_ids, value=payload.value)
    except BulkPartialFailureError as exc:
        _raise_bulk_errors(exc)
    return {"updated": len(payload.post_ids)}


@router.post("/posts/bulk/star")
async def bulk_star(
    payload: BulkFlagRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> dict[str, int]:
    service = _service(session, current_user)
    try:
        await service.bulk_star(current_user, payload.post_ids, value=payload.value)
    except BulkPartialFailureError as exc:
        _raise_bulk_errors(exc)
    return {"updated": len(payload.post_ids)}


@router.post("/posts/bulk/reassign")
async def bulk_reassign(
    payload: BulkReassignRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> dict[str, int]:
    service = _service(session, current_user)
    try:
        await service.bulk_reassign(current_user, payload.post_ids, to_user_id=payload.to_user_id)
    except (
        BulkPartialFailureError,
        BulkReassignForbiddenError,
        ReassignTargetNotActiveError,
    ) as exc:
        _raise_bulk_errors(exc)
    return {"updated": len(payload.post_ids)}
