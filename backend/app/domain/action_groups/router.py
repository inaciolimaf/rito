import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidTransferError
from app.core.http import get_or_404, parse_active_status
from app.core.permissions import UserRole, require_role
from app.domain.action_groups.exceptions import (
    ActionGroupInUseError,
    ActionGroupNameAlreadyExistsError,
    ActionGroupNotFoundError,
    LawsuitTypeNameAlreadyExistsError,
)
from app.domain.action_groups.models import ActionGroup, LawsuitType
from app.domain.action_groups.schemas import (
    ActionGroupCreateRequest,
    ActionGroupListResponse,
    ActionGroupResponse,
    ActionGroupUpdateRequest,
    LawsuitTypeCreateRequest,
    LawsuitTypeListResponse,
    LawsuitTypeResponse,
    LawsuitTypeUpdateRequest,
    TransferLawsuitTypesRequest,
)
from app.domain.action_groups.service import ActionGroupService, LawsuitTypeService
from app.domain.auth.deps import get_session_for_current_user
from app.domain.users.models import User

action_groups_router = APIRouter(prefix="/action-groups", tags=["action-groups"])
lawsuit_types_router = APIRouter(prefix="/lawsuit-types", tags=["lawsuit-types"])


def _group_to_response(group: ActionGroup, count: int) -> ActionGroupResponse:
    return ActionGroupResponse(
        id=group.id,
        name=group.name,
        publications_user_id=group.publications_user_id,
        is_active=group.is_active,
        lawsuit_types_count=count,
        created_at=group.created_at,
    )


def _type_to_response(lawsuit_type: LawsuitType, group_name: str) -> LawsuitTypeResponse:
    return LawsuitTypeResponse(
        id=lawsuit_type.id,
        name=lawsuit_type.name,
        action_group_id=lawsuit_type.action_group_id,
        action_group_name=group_name,
        is_active=lawsuit_type.is_active,
        created_at=lawsuit_type.created_at,
    )


@action_groups_router.get("")
async def list_action_groups(
    status_: Literal["active", "inactive"] | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> ActionGroupListResponse:
    service = ActionGroupService(session=session, tenant_id=current_user.tenant_id)
    items = await service.list_groups(is_active=parse_active_status(status_), query=q)
    return ActionGroupListResponse(
        items=[_group_to_response(group, count) for group, count in items], total=len(items)
    )


@action_groups_router.post("", status_code=201)
async def create_action_group(
    payload: ActionGroupCreateRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> ActionGroupResponse:
    service = ActionGroupService(session=session, tenant_id=current_user.tenant_id)
    try:
        group = await service.create(payload)
    except ActionGroupNameAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail="Já existe um grupo com esse nome.") from exc
    return _group_to_response(group, 0)


@action_groups_router.put("/{group_id}")
async def update_action_group(
    group_id: uuid.UUID,
    payload: ActionGroupUpdateRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> ActionGroupResponse:
    service = ActionGroupService(session=session, tenant_id=current_user.tenant_id)
    group, count = await get_or_404(lambda: service.get(group_id), "Grupo de ação não encontrado.")

    try:
        updated = await service.update(group, payload)
    except ActionGroupNameAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail="Já existe um grupo com esse nome.") from exc
    return _group_to_response(updated, count)


@action_groups_router.delete("/{group_id}", status_code=204)
async def delete_action_group(
    group_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    service = ActionGroupService(session=session, tenant_id=current_user.tenant_id)
    group, _ = await get_or_404(lambda: service.get(group_id), "Grupo de ação não encontrado.")

    try:
        await service.delete(group)
    except ActionGroupInUseError as exc:
        raise HTTPException(
            status_code=409,
            detail="Grupo tem tipos de ação vinculados — transfira-os antes de excluir.",
        ) from exc


@lawsuit_types_router.get("")
async def list_lawsuit_types(
    group_id: uuid.UUID | None = Query(default=None),
    status_: Literal["active", "inactive"] | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> LawsuitTypeListResponse:
    service = LawsuitTypeService(session=session, tenant_id=current_user.tenant_id)
    items = await service.list_types(
        action_group_id=group_id, is_active=parse_active_status(status_), query=q
    )
    return LawsuitTypeListResponse(
        items=[_type_to_response(item, group_name) for item, group_name in items], total=len(items)
    )


@lawsuit_types_router.post("", status_code=201)
async def create_lawsuit_type(
    payload: LawsuitTypeCreateRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> LawsuitTypeResponse:
    service = LawsuitTypeService(session=session, tenant_id=current_user.tenant_id)
    try:
        lawsuit_type, group_name = await service.create(payload)
    except LawsuitTypeNameAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail="Já existe um tipo com esse nome.") from exc
    except ActionGroupNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Grupo de ação não encontrado.") from exc
    return _type_to_response(lawsuit_type, group_name)


@lawsuit_types_router.post("/transfer")
async def transfer_lawsuit_types(
    payload: TransferLawsuitTypesRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> dict[str, int]:
    service = LawsuitTypeService(session=session, tenant_id=current_user.tenant_id)
    try:
        transferred = await service.transfer(from_id=payload.from_id, to_id=payload.to_id)
    except InvalidTransferError as exc:
        raise HTTPException(
            status_code=422, detail="from_id/to_id inválidos — precisam ser grupos distintos."
        ) from exc
    return {"transferred_count": transferred}


@lawsuit_types_router.put("/{type_id}")
async def update_lawsuit_type(
    type_id: uuid.UUID,
    payload: LawsuitTypeUpdateRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> LawsuitTypeResponse:
    service = LawsuitTypeService(session=session, tenant_id=current_user.tenant_id)
    lawsuit_type, _ = await get_or_404(lambda: service.get(type_id), "Tipo de ação não encontrado.")

    try:
        updated, group_name = await service.update(lawsuit_type, payload)
    except LawsuitTypeNameAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail="Já existe um tipo com esse nome.") from exc
    except ActionGroupNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Grupo de ação não encontrado.") from exc
    return _type_to_response(updated, group_name)


@lawsuit_types_router.delete("/{type_id}", status_code=204)
async def delete_lawsuit_type(
    type_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    service = LawsuitTypeService(session=session, tenant_id=current_user.tenant_id)
    lawsuit_type, _ = await get_or_404(lambda: service.get(type_id), "Tipo de ação não encontrado.")
    await service.delete(lawsuit_type)
