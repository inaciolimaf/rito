import uuid
from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_transactional_email
from app.core.permissions import UserRole, require_role
from app.core.transactional_email import TransactionalEmailSender
from app.domain.auth.deps import get_session_for_current_user
from app.domain.partnerships.exceptions import (
    InvalidInviteError,
    InvalidTaskTypeError,
    LawsuitNotSharedError,
    PartnershipAlreadyExistsError,
    PartnershipNotFoundError,
    SharingForbiddenError,
)
from app.domain.partnerships.models import PartnershipStatus, SharedLawsuit
from app.domain.partnerships.schemas import (
    PartnershipAcceptRequest,
    PartnershipInviteRequest,
    PartnershipInviteResponse,
    PartnershipListResponse,
    PartnershipResponse,
    PartnershipSummaryResponse,
    PartnerTaskCreateRequest,
    SharedLawsuitDetailResponse,
    SharedLawsuitListResponse,
    SharedLawsuitResponse,
    SharedMovementResponse,
    SharedPartyResponse,
    SharedTaskResponse,
    SharedTaskTypeResponse,
    SharedWithMeItem,
    SharedWithMeReport,
    SharedWithMeResponse,
    ShareLawsuitRequest,
)
from app.domain.partnerships.service import PartnershipService, PartnershipView
from app.domain.users.models import User

router = APIRouter(prefix="/partnerships", tags=["partnerships"])
lawsuit_sharing_router = APIRouter(prefix="/lawsuits", tags=["partnerships"])

_NOT_SHARED_DETAIL = "Processo não compartilhado com este escritório."
_PARTNERSHIP_NOT_FOUND_DETAIL = "Parceria não encontrada."


def _to_partnership_response(view: PartnershipView) -> PartnershipResponse:
    partnership = view.partnership
    return PartnershipResponse(
        id=partnership.id,
        status=partnership.status,
        invited_email=str(partnership.invited_email),
        partner_tenant_id=(
            partnership.partner_tenant_id if view.is_requester else partnership.requester_tenant_id
        ),
        partner_name=view.partner_name,
        is_requester=view.is_requester,
        shared_count=view.shared_count,
        accepted_at=partnership.accepted_at,
        created_at=partnership.created_at,
    )


def _to_share_response(share: SharedLawsuit, partner_name: str | None) -> SharedLawsuitResponse:
    return SharedLawsuitResponse(
        id=share.id,
        lawsuit_id=share.lawsuit_id,
        partnership_id=share.partnership_id,
        partner_tenant_id=share.partner_tenant_id,
        partner_name=partner_name,
        can_view_financial=share.can_view_financial,
        can_create_tasks=share.can_create_tasks,
        revoked_at=share.revoked_at,
        created_at=share.created_at,
    )


def _to_shared_item(row: Row[Any]) -> SharedWithMeItem:
    return SharedWithMeItem(
        share_id=row.share_id,
        lawsuit_id=row.lawsuit_id,
        partnership_id=row.partnership_id,
        owner_tenant_id=row.owner_tenant_id,
        owner_name=row.owner_name,
        process_number=row.process_number,
        folder=row.folder,
        stage_name=row.stage_name,
        step_id=row.step_id,
        can_view_financial=row.can_view_financial,
        can_create_tasks=row.can_create_tasks,
        case_value=row.case_value,
        fees_value=row.fees_value,
        open_tasks=int(row.open_tasks),
        shared_at=row.shared_at,
    )


def _service(session: AsyncSession, current_user: User) -> PartnershipService:
    return PartnershipService(session=session, tenant_id=current_user.tenant_id)


# --------------------------------------------------- compartilhado comigo (parceiro)
# Registradas antes de `/{partnership_id}/...` de propósito: "shared-with-me" não
# parseia como UUID e cairia em 422 se a rota por id ganhasse o match primeiro.


@router.get("/shared-with-me")
async def list_shared_with_me(
    report: bool = Query(default=False),
    steps: list[int] | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> SharedWithMeResponse:
    service = _service(session, current_user)
    rows = await service.shared_with_me(steps=steps)
    items = [_to_shared_item(row) for row in rows]
    built_report = None
    if report:
        by_step = Counter(item.stage_name for item in items)
        built_report = SharedWithMeReport(
            lawsuits_by_step=dict(by_step),
            open_tasks=sum(item.open_tasks for item in items),
        )
    return SharedWithMeResponse(items=items, total=len(items), report=built_report)


@router.get("/shared-with-me/{lawsuit_id}")
async def get_shared_lawsuit(
    lawsuit_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> SharedLawsuitDetailResponse:
    service = _service(session, current_user)
    try:
        detail = await service.shared_detail(lawsuit_id)
    except LawsuitNotSharedError as exc:
        raise HTTPException(status_code=404, detail=_NOT_SHARED_DETAIL) from exc
    return SharedLawsuitDetailResponse(
        lawsuit=_to_shared_item(detail.lawsuit),
        parties=[
            SharedPartyResponse(pole=row.pole, name=row.name, is_client=row.is_client)
            for row in detail.parties
        ],
        timeline=[
            SharedMovementResponse(
                id=row.id,
                occurred_at=row.occurred_at,
                title=row.title,
                body=row.body,
                origin=row.origin,
            )
            for row in detail.timeline
        ],
        tasks=[
            SharedTaskResponse(
                id=row.id,
                task_type_name=row.task_type_name,
                scheduled_date=row.scheduled_date,
                deadline_date=row.deadline_date,
                comments=row.comments,
                completed=row.completed,
                from_partner=row.from_partner,
                created_at=row.created_at,
            )
            for row in detail.tasks
        ],
    )


@router.get("/shared-with-me/{lawsuit_id}/task-types")
async def list_shared_task_types(
    lawsuit_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> list[SharedTaskTypeResponse]:
    service = _service(session, current_user)
    try:
        rows = await service.shared_task_types(lawsuit_id)
    except LawsuitNotSharedError as exc:
        raise HTTPException(status_code=404, detail=_NOT_SHARED_DETAIL) from exc
    return [SharedTaskTypeResponse(id=row.id, name=row.name) for row in rows]


@router.post("/shared-with-me/{lawsuit_id}/tasks", status_code=201)
async def create_partner_task(
    lawsuit_id: uuid.UUID,
    payload: PartnerTaskCreateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> dict[str, uuid.UUID]:
    """Regra 5/8: a tarefa nasce no escritório DONO, marcada com a origem, e cai na
    caixa de entrada do responsável pelo processo lá."""
    service = _service(session, current_user)
    try:
        post_id = await service.create_partner_task(
            actor=current_user, lawsuit_id=lawsuit_id, payload=payload
        )
    except LawsuitNotSharedError as exc:
        raise HTTPException(status_code=404, detail=_NOT_SHARED_DETAIL) from exc
    except SharingForbiddenError as exc:
        raise HTTPException(
            status_code=403, detail="Este compartilhamento não permite criar tarefas."
        ) from exc
    except InvalidTaskTypeError as exc:
        raise HTTPException(status_code=422, detail="Tipo de tarefa inválido.") from exc
    return {"post_id": post_id}


@router.get("/summary")
async def get_partnership_summary(
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PartnershipSummaryResponse:
    service = _service(session, current_user)
    shared, pending_here, pending_partner, partners = await service.summary()
    return PartnershipSummaryResponse(
        shared_lawsuits=shared,
        pending_by_office=pending_here,
        pending_by_partner=pending_partner,
        active_partners=partners,
    )


# ------------------------------------------------------------------------ rede


@router.get("")
async def list_partnerships(
    status_: PartnershipStatus | None = Query(default=None, alias="status"),
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PartnershipListResponse:
    service = _service(session, current_user)
    views = await service.list_partnerships(status=status_)
    return PartnershipListResponse(
        items=[_to_partnership_response(view) for view in views], total=len(views)
    )


@router.post("/invite", status_code=201)
async def invite_partner(
    payload: PartnershipInviteRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    email_sender: TransactionalEmailSender = Depends(get_transactional_email),
) -> PartnershipInviteResponse:
    service = _service(session, current_user)
    try:
        view, token, account_exists = await service.invite(
            actor=current_user, email=str(payload.email)
        )
    except PartnershipAlreadyExistsError as exc:
        raise HTTPException(
            status_code=409, detail="Já existe convite ou parceria para este e-mail."
        ) from exc
    # Regra 19 (spec 102): o token vai por e-mail e NÃO volta no corpo. Devolvê-lo era o
    # contorno de não haver envio (spec 079) — um segredo de uso único não deve trafegar
    # para quem pediu a criação, e sim para quem vai usá-lo. `account_exists` continua,
    # que é o que distingue os dois convites da regra 2 (parceria x cadastro).
    nomes = await service.partnerships.tenant_names({current_user.tenant_id})
    await email_sender.send_partnership_invite(
        to=str(payload.email),
        token=token,
        office_name=nomes.get(current_user.tenant_id, "um escritório"),
    )
    return PartnershipInviteResponse(
        partnership=_to_partnership_response(view),
        account_exists=account_exists,
    )


@router.post("/accept")
async def accept_partnership(
    payload: PartnershipAcceptRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PartnershipResponse:
    service = _service(session, current_user)
    try:
        view = await service.accept(actor=current_user, token=payload.token)
    except InvalidInviteError as exc:
        raise HTTPException(status_code=400, detail="Convite inválido ou já utilizado.") from exc
    return _to_partnership_response(view)


@router.post("/{partnership_id}/end", status_code=204)
async def end_partnership(
    partnership_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    service = _service(session, current_user)
    try:
        await service.end(actor=current_user, partnership_id=partnership_id)
    except PartnershipNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_PARTNERSHIP_NOT_FOUND_DETAIL) from exc


# ------------------------------------------------------- compartilhar (lado dono)


@lawsuit_sharing_router.get("/{lawsuit_id}/shares")
async def list_lawsuit_shares(
    lawsuit_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> SharedLawsuitListResponse:
    """Alimenta o badge permanente do processo (regra 12) — por isso COLABORADOR lê."""
    service = _service(session, current_user)
    shares = await service.list_shares(lawsuit_id)
    return SharedLawsuitListResponse(
        items=[_to_share_response(share, name) for share, name in shares],
        total=len(shares),
    )


@lawsuit_sharing_router.post("/{lawsuit_id}/share", status_code=201)
async def share_lawsuit(
    lawsuit_id: uuid.UUID,
    payload: ShareLawsuitRequest,
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> SharedLawsuitResponse:
    service = _service(session, current_user)
    try:
        share = await service.share_lawsuit(
            actor=current_user, lawsuit_id=lawsuit_id, payload=payload
        )
    except LawsuitNotSharedError as exc:
        raise HTTPException(status_code=404, detail="Processo não encontrado.") from exc
    except PartnershipNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_PARTNERSHIP_NOT_FOUND_DETAIL) from exc
    names = await service.partnerships.tenant_names({share.partner_tenant_id})
    return _to_share_response(share, names.get(share.partner_tenant_id))


@lawsuit_sharing_router.delete("/{lawsuit_id}/share/{share_id}", status_code=204)
async def revoke_lawsuit_share(
    lawsuit_id: uuid.UUID,
    share_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    service = _service(session, current_user)
    try:
        await service.revoke_share(actor=current_user, lawsuit_id=lawsuit_id, share_id=share_id)
    except LawsuitNotSharedError as exc:
        raise HTTPException(status_code=404, detail=_NOT_SHARED_DETAIL) from exc
