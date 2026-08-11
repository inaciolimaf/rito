import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidTransferError
from app.core.http import get_or_404, parse_active_status
from app.core.permissions import FinancialAccess, UserRole, require_financial, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.financial.exceptions import (
    BankAccountNameAlreadyExistsError,
    CostCenterNameAlreadyExistsError,
    DefaultAccountNeedsReplacementError,
    DefaultCategoryNotDeletableError,
    DefaultCostCenterNotDeletableError,
    DreGroupNotFoundError,
    FinancialCategoryNameAlreadyExistsError,
    InstitutionNotFoundError,
)
from app.domain.financial.models import (
    AccountKind,
    BankAccount,
    CostCenter,
    EntryType,
    FinancialCategory,
)
from app.domain.financial.schemas import (
    AccountBalanceResponse,
    BankAccountCreateRequest,
    BankAccountListResponse,
    BankAccountResponse,
    BankAccountUpdateRequest,
    CostCenterCreateRequest,
    CostCenterListResponse,
    CostCenterResponse,
    CostCenterUpdateRequest,
    DreGroupResponse,
    FinancialCategoryCreateRequest,
    FinancialCategoryListResponse,
    FinancialCategoryResponse,
    FinancialCategoryUpdateRequest,
    FinancialInstitutionListResponse,
    FinancialInstitutionResponse,
    TransferCostCentersRequest,
    TransferFinancialCategoriesRequest,
)
from app.domain.financial.service import (
    BankAccountService,
    CostCenterService,
    DreGroupService,
    FinancialCategoryService,
    FinancialInstitutionService,
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


def _account_to_response(account: BankAccount, institution_name: str | None) -> BankAccountResponse:
    return BankAccountResponse(
        id=account.id,
        kind=account.kind,
        name=account.name,
        institution_id=account.institution_id,
        institution_name=institution_name,
        agency=account.agency,
        account_number=account.account_number,
        cycle_day=account.cycle_day,
        due_day=account.due_day,
        initial_amount=account.initial_amount,
        is_default=account.is_default,
        is_active=account.is_active,
        created_at=account.created_at,
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


@router.get("/financial-institutions")
async def list_financial_institutions(
    q: str | None = Query(default=None),
    _current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> FinancialInstitutionListResponse:
    """Autenticado só — sem gate de `financial_access` (regra genérica de referência,
    mesmo padrão de `/courts`/`/steps`)."""
    institutions = await FinancialInstitutionService(session).list_institutions(query=q)
    return FinancialInstitutionListResponse(
        items=[
            FinancialInstitutionResponse(id=i.id, name=i.name, compe_code=i.compe_code)
            for i in institutions
        ]
    )


@router.get("/bank-accounts")
async def list_bank_accounts(
    kind: AccountKind | None = Query(default=None),
    status_: Literal["active", "inactive"] | None = Query(default=None, alias="status"),
    current_user: User = Depends(require_financial(FinancialAccess.READ_ONLY)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> BankAccountListResponse:
    service = BankAccountService(session=session, tenant_id=current_user.tenant_id)
    items = await service.list_accounts(kind=kind, is_active=parse_active_status(status_))
    return BankAccountListResponse(
        items=[_account_to_response(account, name) for account, name in items], total=len(items)
    )


@router.post("/bank-accounts", status_code=201)
async def create_bank_account(
    payload: BankAccountCreateRequest,
    current_user: User = Depends(require_financial(FinancialAccess.FULL)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> BankAccountResponse:
    service = BankAccountService(session=session, tenant_id=current_user.tenant_id)
    try:
        account, institution_name = await service.create(payload)
    except BankAccountNameAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail="Já existe uma conta com esse nome.") from exc
    except InstitutionNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Instituição não encontrada.") from exc
    return _account_to_response(account, institution_name)


@router.put("/bank-accounts/{account_id}")
async def update_bank_account(
    account_id: uuid.UUID,
    payload: BankAccountUpdateRequest,
    current_user: User = Depends(require_financial(FinancialAccess.FULL)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> BankAccountResponse:
    service = BankAccountService(session=session, tenant_id=current_user.tenant_id)
    account, _ = await get_or_404(lambda: service.get(account_id), "Conta não encontrada.")
    try:
        updated, institution_name = await service.update(account, payload)
    except BankAccountNameAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail="Já existe uma conta com esse nome.") from exc
    except InstitutionNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Instituição não encontrada.") from exc
    except DefaultAccountNeedsReplacementError as exc:
        raise HTTPException(
            status_code=409,
            detail="Eleja outra conta padrão antes de inativar esta.",
        ) from exc
    return _account_to_response(updated, institution_name)


@router.delete("/bank-accounts/{account_id}", status_code=204)
async def delete_bank_account(
    account_id: uuid.UUID,
    current_user: User = Depends(require_financial(FinancialAccess.FULL)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    service = BankAccountService(session=session, tenant_id=current_user.tenant_id)
    account, _ = await get_or_404(lambda: service.get(account_id), "Conta não encontrada.")
    await service.delete(account)


@router.post("/bank-accounts/{account_id}/set-default")
async def set_default_bank_account(
    account_id: uuid.UUID,
    current_user: User = Depends(require_financial(FinancialAccess.FULL)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> BankAccountResponse:
    service = BankAccountService(session=session, tenant_id=current_user.tenant_id)
    account, institution_name = await get_or_404(
        lambda: service.get(account_id), "Conta não encontrada."
    )
    updated = await service.set_default(account)
    return _account_to_response(updated, institution_name)


@router.get("/bank-accounts/{account_id}/balance")
async def get_bank_account_balance(
    account_id: uuid.UUID,
    at: date | None = Query(default=None),
    current_user: User = Depends(require_financial(FinancialAccess.READ_ONLY)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> AccountBalanceResponse:
    """Regras 3/4 completas na spec 056 (dependem de lançamentos) — por enquanto
    devolve o saldo inicial (ver Descobertas)."""
    service = BankAccountService(session=session, tenant_id=current_user.tenant_id)
    account, _ = await get_or_404(lambda: service.get(account_id), "Conta não encontrada.")
    balance = await service.get_balance(account, at=at)
    return AccountBalanceResponse(
        account_id=account.id, kind=account.kind, balance=balance, as_of=at or date.today()
    )
