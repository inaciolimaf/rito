import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.customer_origins.exceptions import (
    CustomerOriginNameAlreadyExistsError,
    InvalidTransferError,
)
from app.domain.customer_origins.models import CustomerOrigin
from app.domain.customer_origins.schemas import (
    CustomerOriginCreateRequest,
    CustomerOriginListResponse,
    CustomerOriginResponse,
    CustomerOriginUpdateRequest,
    TransferCustomerOriginsRequest,
)
from app.domain.customer_origins.service import CustomerOriginService
from app.domain.users.models import User

router = APIRouter(prefix="/customer-origins", tags=["customer-origins"])


def _origin_to_response(origin: CustomerOrigin) -> CustomerOriginResponse:
    return CustomerOriginResponse(
        id=origin.id, name=origin.name, is_active=origin.is_active, created_at=origin.created_at
    )


@router.get("")
async def list_customer_origins(
    status_: Literal["active", "inactive"] | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> CustomerOriginListResponse:
    is_active = {"active": True, "inactive": False}.get(status_) if status_ else None
    service = CustomerOriginService(session=session, tenant_id=current_user.tenant_id)
    items = await service.list_origins(is_active=is_active, query=q)
    return CustomerOriginListResponse(
        items=[_origin_to_response(item) for item in items], total=len(items)
    )


@router.post("", status_code=201)
async def create_customer_origin(
    payload: CustomerOriginCreateRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> CustomerOriginResponse:
    service = CustomerOriginService(session=session, tenant_id=current_user.tenant_id)
    try:
        origin = await service.create(payload)
    except CustomerOriginNameAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail="Já existe uma origem com esse nome.") from exc
    return _origin_to_response(origin)


@router.put("/{origin_id}")
async def update_customer_origin(
    origin_id: uuid.UUID,
    payload: CustomerOriginUpdateRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> CustomerOriginResponse:
    service = CustomerOriginService(session=session, tenant_id=current_user.tenant_id)
    origin = await service.get(origin_id)
    if origin is None:
        raise HTTPException(status_code=404, detail="Origem não encontrada.")

    try:
        updated = await service.update(origin, payload)
    except CustomerOriginNameAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail="Já existe uma origem com esse nome.") from exc
    return _origin_to_response(updated)


@router.delete("/{origin_id}", status_code=204)
async def delete_customer_origin(
    origin_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    service = CustomerOriginService(session=session, tenant_id=current_user.tenant_id)
    origin = await service.get(origin_id)
    if origin is None:
        raise HTTPException(status_code=404, detail="Origem não encontrada.")
    await service.delete(origin)


@router.post("/transfer")
async def transfer_customer_origins(
    payload: TransferCustomerOriginsRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> dict[str, int]:
    service = CustomerOriginService(session=session, tenant_id=current_user.tenant_id)
    try:
        transferred = await service.transfer(from_id=payload.from_id, to_id=payload.to_id)
    except InvalidTransferError as exc:
        raise HTTPException(
            status_code=422, detail="from_id/to_id inválidos — precisam ser origens distintas."
        ) from exc
    return {"transferred_count": transferred}
