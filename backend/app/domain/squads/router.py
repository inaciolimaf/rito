import uuid
from collections.abc import Sequence
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_file_storage
from app.core.http import get_or_404, parse_active_status
from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.squads.exceptions import SquadNameAlreadyExistsError
from app.domain.squads.models import Squad
from app.domain.squads.schemas import (
    SquadCreateRequest,
    SquadListResponse,
    SquadMemberSummary,
    SquadResponse,
    SquadUpdateRequest,
)
from app.domain.squads.service import SquadService
from app.domain.users.models import User
from app.integrations.storage.base import FileStorage

router = APIRouter(prefix="/squads", tags=["squads"])

_DEFAULT_PAGE_SIZE = 20


def _to_response(squad: Squad, members: Sequence[User], storage: FileStorage) -> SquadResponse:
    return SquadResponse(
        id=squad.id,
        name=squad.name,
        is_active=squad.is_active,
        members=[
            SquadMemberSummary(
                id=member.id,
                name=member.name,
                avatar_url=storage.public_url(member.avatar_key) if member.avatar_key else None,
            )
            for member in members
        ],
        created_at=squad.created_at,
        updated_at=squad.updated_at,
    )


@router.get("")
async def list_squads(
    status_: Literal["active", "inactive"] | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=100),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> SquadListResponse:
    service = SquadService(session=session, tenant_id=current_user.tenant_id)
    items, next_cursor, total = await service.list_squads(
        is_active=parse_active_status(status_), query=q, cursor=cursor, limit=limit
    )
    return SquadListResponse(
        items=[_to_response(squad, members, storage) for squad, members in items],
        next_cursor=next_cursor,
        total=total,
    )


@router.post("", status_code=201)
async def create_squad(
    payload: SquadCreateRequest,
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> SquadResponse:
    service = SquadService(session=session, tenant_id=current_user.tenant_id)
    try:
        squad, members = await service.create(payload)
    except SquadNameAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail="Já existe um time com esse nome.") from exc
    return _to_response(squad, members, storage)


@router.get("/{squad_id}")
async def get_squad(
    squad_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> SquadResponse:
    service = SquadService(session=session, tenant_id=current_user.tenant_id)
    squad, members = await get_or_404(lambda: service.get(squad_id), "Time não encontrado.")
    return _to_response(squad, members, storage)


@router.put("/{squad_id}")
async def update_squad(
    squad_id: uuid.UUID,
    payload: SquadUpdateRequest,
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> SquadResponse:
    service = SquadService(session=session, tenant_id=current_user.tenant_id)
    squad, _ = await get_or_404(lambda: service.get(squad_id), "Time não encontrado.")

    try:
        updated_squad, members = await service.update(squad, payload)
    except SquadNameAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail="Já existe um time com esse nome.") from exc
    return _to_response(updated_squad, members, storage)


@router.delete("/{squad_id}", status_code=204)
async def delete_squad(
    squad_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    service = SquadService(session=session, tenant_id=current_user.tenant_id)
    squad, _ = await get_or_404(lambda: service.get(squad_id), "Time não encontrado.")
    await service.delete(squad)
