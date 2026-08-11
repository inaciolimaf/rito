import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidTransferError
from app.core.http import get_or_404, parse_active_status
from app.core.permissions import FinancialAccess, UserRole, require_financial, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.financial.exceptions import (
    CostCenterNameAlreadyExistsError,
    DefaultCategoryNotDeletableError,
    DefaultCostCenterNotDeletableError,
    DreGroupNotFoundError,
    FinancialCategoryNameAlreadyExistsError,
)
from app.domain.financial.models import CostCenter, EntryType, FinancialCategory
from app.domain.financial.schemas import (
    CostCenterCreateRequest,
    CostCenterListResponse,
    CostCenterResponse,
    CostCenterUpdateRequest,
    DreGroupResponse,
    FinancialCategoryCreateRequest,
    FinancialCategoryListResponse,
    FinancialCategoryResponse,
    FinancialCategoryUpdateRequest,
    TransferCostCentersRequest,
    TransferFinancialCategoriesRequest,
)
from app.domain.financial.service import (
    CostCenterService,
    DreGroupService,
    FinancialCategoryService,
)
from app.domain.users.models import User

router = APIRouter(tags=["financial"])


def _category_to_response(
    category: FinancialCategory, group_name: str
) -> FinancialCategoryResponse:
    return FinancialCategoryResponse(
        id=category.id,
        name=category.name,
        type=category.type,
        dre_group_id=category.dre_group_id,
        dre_group_name=group_name,
        is_default=category.is_default,
        is_active=category.is_active,
        created_at=category.created_at,
    )


def _cost_center_to_response(cost_center: CostCenter) -> CostCenterResponse:
    return CostCenterResponse(
        id=cost_center.id,
        name=cost_center.name,
        is_default=cost_center.is_default,
        is_active=cost_center.is_active,
        created_at=cost_center.created_at,
    )


@router.get("/dre-groups")
async def list_dre_groups(
    _current_user: User = Depends(require_financial(FinancialAccess.READ_ONLY)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> list[DreGroupResponse]:
    """Regra 1: os 10 grupos são imutáveis — só leitura, sem POST/PUT/DELETE."""
    groups = await DreGroupService(session).list_groups()
    return [DreGroupResponse(id=group.id, name=group.name, nature=group.nature) for group in groups]


@router.get("/financial-categories")
async def list_financial_categories(
    type: EntryType | None = Query(default=None),  # noqa: A002 (nome do contrato de API)
    group: int | None = Query(default=None),
    status_: Literal["active", "inactive"] | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
    current_user: User = Depends(require_financial(FinancialAccess.READ_ONLY)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> FinancialCategoryListResponse:
    service = FinancialCategoryService(session=session, tenant_id=current_user.tenant_id)
    items = await service.list_categories(
        type_=type, dre_group_id=group, is_active=parse_active_status(status_), query=q
    )
    return FinancialCategoryListResponse(
        items=[_category_to_response(category, group_name) for category, group_name in items],
        total=len(items),
    )


@router.post("/financial-categories", status_code=201)
async def create_financial_category(
    payload: FinancialCategoryCreateRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    _financial: User = Depends(require_financial(FinancialAccess.FULL)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> FinancialCategoryResponse:
    service = FinancialCategoryService(session=session, tenant_id=current_user.tenant_id)
    try:
        category, group_name = await service.create(payload)
    except FinancialCategoryNameAlreadyExistsError as exc:
        raise HTTPException(
            status_code=409, detail="Já existe uma categoria com esse nome."
        ) from exc
    except DreGroupNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Grupo DRE não encontrado.") from exc
    return _category_to_response(category, group_name)


@router.put("/financial-categories/{category_id}")
async def update_financial_category(
    category_id: uuid.UUID,
    payload: FinancialCategoryUpdateRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    _financial: User = Depends(require_financial(FinancialAccess.FULL)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> FinancialCategoryResponse:
    service = FinancialCategoryService(session=session, tenant_id=current_user.tenant_id)
    category, _ = await get_or_404(lambda: service.get(category_id), "Categoria não encontrada.")
    try:
        updated, group_name = await service.update(category, payload)
    except FinancialCategoryNameAlreadyExistsError as exc:
        raise HTTPException(
            status_code=409, detail="Já existe uma categoria com esse nome."
        ) from exc
    except DreGroupNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Grupo DRE não encontrado.") from exc
    return _category_to_response(updated, group_name)


@router.delete("/financial-categories/{category_id}", status_code=204)
async def delete_financial_category(
    category_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    _financial: User = Depends(require_financial(FinancialAccess.FULL)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    service = FinancialCategoryService(session=session, tenant_id=current_user.tenant_id)
    category, _ = await get_or_404(lambda: service.get(category_id), "Categoria não encontrada.")
    try:
        await service.delete(category)
    except DefaultCategoryNotDeletableError as exc:
        raise HTTPException(
            status_code=409,
            detail="Categoria padrão não pode ser excluída — inative-a em vez disso.",
        ) from exc


@router.post("/financial-categories/transfer")
async def transfer_financial_categories(
    payload: TransferFinancialCategoriesRequest,
    current_user: User = Depends(require_financial(FinancialAccess.FULL)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> dict[str, int]:
    service = FinancialCategoryService(session=session, tenant_id=current_user.tenant_id)
    try:
        transferred = await service.transfer(from_id=payload.from_id, to_id=payload.to_id)
    except InvalidTransferError as exc:
        raise HTTPException(
            status_code=422, detail="from_id/to_id inválidos — precisam ser categorias distintas."
        ) from exc
    return {"transferred_count": transferred}


@router.get("/cost-centers")
async def list_cost_centers(
    status_: Literal["active", "inactive"] | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
    current_user: User = Depends(require_financial(FinancialAccess.READ_ONLY)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> CostCenterListResponse:
    service = CostCenterService(session=session, tenant_id=current_user.tenant_id)
    items = await service.list_cost_centers(is_active=parse_active_status(status_), query=q)
    return CostCenterListResponse(
        items=[_cost_center_to_response(item) for item in items], total=len(items)
    )


@router.post("/cost-centers", status_code=201)
async def create_cost_center(
    payload: CostCenterCreateRequest,
    current_user: User = Depends(require_financial(FinancialAccess.FULL)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> CostCenterResponse:
    service = CostCenterService(session=session, tenant_id=current_user.tenant_id)
    try:
        cost_center = await service.create(payload)
    except CostCenterNameAlreadyExistsError as exc:
        raise HTTPException(
            status_code=409, detail="Já existe um centro de custo com esse nome."
        ) from exc
    return _cost_center_to_response(cost_center)


@router.put("/cost-centers/{cost_center_id}")
async def update_cost_center(
    cost_center_id: uuid.UUID,
    payload: CostCenterUpdateRequest,
    current_user: User = Depends(require_financial(FinancialAccess.FULL)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> CostCenterResponse:
    service = CostCenterService(session=session, tenant_id=current_user.tenant_id)
    cost_center = await get_or_404(
        lambda: service.get(cost_center_id), "Centro de custo não encontrado."
    )
    try:
        updated = await service.update(cost_center, payload)
    except CostCenterNameAlreadyExistsError as exc:
        raise HTTPException(
            status_code=409, detail="Já existe um centro de custo com esse nome."
        ) from exc
    return _cost_center_to_response(updated)


@router.delete("/cost-centers/{cost_center_id}", status_code=204)
async def delete_cost_center(
    cost_center_id: uuid.UUID,
    current_user: User = Depends(require_financial(FinancialAccess.FULL)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    service = CostCenterService(session=session, tenant_id=current_user.tenant_id)
    cost_center = await get_or_404(
        lambda: service.get(cost_center_id), "Centro de custo não encontrado."
    )
    try:
        await service.delete(cost_center)
    except DefaultCostCenterNotDeletableError as exc:
        raise HTTPException(
            status_code=409,
            detail="O centro de custo GERAL não pode ser excluído — inative-o em vez disso.",
        ) from exc


@router.post("/cost-centers/transfer")
async def transfer_cost_centers(
    payload: TransferCostCentersRequest,
    current_user: User = Depends(require_financial(FinancialAccess.FULL)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> dict[str, int]:
    service = CostCenterService(session=session, tenant_id=current_user.tenant_id)
    try:
        transferred = await service.transfer(from_id=payload.from_id, to_id=payload.to_id)
    except InvalidTransferError as exc:
        raise HTTPException(
            status_code=422,
            detail="from_id/to_id inválidos — precisam ser centros de custo distintos.",
        ) from exc
    return {"transferred_count": transferred}
