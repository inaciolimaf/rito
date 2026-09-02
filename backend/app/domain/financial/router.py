import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock
from app.core.deps import get_file_storage
from app.core.exceptions import InvalidTransferError
from app.core.export import ExportColumn, TableExport
from app.core.http import get_or_404, parse_active_status, parse_month_query
from app.core.permissions import FinancialAccess, UserRole, require_financial, require_role
from app.domain.attachments.rules import AttachmentTooLargeError, AttachmentTypeBlockedError
from app.domain.attachments.service import (
    AttachmentResponse,
    AttachmentService,
    AttachmentTargetNotFoundError,
    TransactionAttachmentLimitError,
)
from app.domain.auth.deps import get_clock, get_session_for_current_user
from app.domain.financial.dashboard import (
    ChartGroupBy,
    Regime,
    get_account_balances,
    get_cash_flow_series,
    get_chart_series,
    get_dashboard_stats,
)
from app.domain.financial.exceptions import (
    BankAccountInUseError,
    BankAccountNameAlreadyExistsError,
    CostCenterInUseError,
    CostCenterNameAlreadyExistsError,
    DefaultAccountNeedsReplacementError,
    DefaultCategoryNotDeletableError,
    DefaultCostCenterNotDeletableError,
    DreGroupNotFoundError,
    FinancialCategoryInUseError,
    FinancialCategoryNameAlreadyExistsError,
    FuturePaymentDateError,
    InitialAmountLockedError,
    InstitutionNotFoundError,
    PaidTransactionCannotBecomeInternalError,
    PaidTransactionNotDeletableError,
    SeriesHasPaidTransactionError,
    TransactionAccountNotFoundError,
    TransactionCategoryNotFoundError,
    TransactionCategoryTypeMismatchError,
    TransactionCostCenterNotFoundError,
    TransactionCustomerNotFoundError,
    TransactionLawsuitNotFoundError,
)
from app.domain.financial.models import (
    AccountKind,
    BankAccount,
    CostCenter,
    EntryType,
    FinancialCategory,
    TransactionKind,
    TransactionSeries,
)
from app.domain.financial.reports import ReportGroupRow, ReportRegime, get_financial_report
from app.domain.financial.schemas import (
    AccountBalanceItem,
    AccountBalanceResponse,
    BankAccountBalancesResponse,
    BankAccountCreateRequest,
    BankAccountListResponse,
    BankAccountResponse,
    BankAccountUpdateRequest,
    CashFlowPointResponse,
    CashFlowResponse,
    ChartPointResponse,
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
    FinancialReportExportRequest,
    FinancialReportResponse,
    PayTransactionRequest,
    ReportGroupRowResponse,
    SeriesPreviewItem,
    SeriesPreviewResponse,
    TransactionChartResponse,
    TransactionCreateRequest,
    TransactionListResponse,
    TransactionResponse,
    TransactionRow,
    TransactionSeriesResponse,
    TransactionSeriesUpdateRequest,
    TransactionStatsResponse,
    TransactionTotalsResponse,
    TransactionUpdateRequest,
    TransferCostCentersRequest,
    TransferFinancialCategoriesRequest,
)
from app.domain.financial.service import (
    BankAccountService,
    CostCenterService,
    DreGroupService,
    FinancialCategoryService,
    FinancialInstitutionService,
    TransactionSeriesService,
    TransactionService,
)
from app.domain.users.models import User
from app.integrations.storage.base import FileStorage
from app.workers.aggregates import schedule_aggregate_refresh

# Spec 098, regra 3: a listagem de lançamentos pagina como todas as outras.
_DEFAULT_PAGE_SIZE = 50

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


def _transaction_to_response(row: TransactionRow) -> TransactionResponse:
    transaction = row.transaction
    return TransactionResponse(
        id=transaction.id,
        kind=transaction.kind,
        user_id=transaction.user_id,
        user_name=row.user_name,
        debit_account_id=transaction.debit_account_id,
        debit_account_name=row.debit_account_name,
        credit_account_id=transaction.credit_account_id,
        credit_account_name=row.credit_account_name,
        category_id=transaction.category_id,
        category_name=row.category_name,
        cost_center_id=transaction.cost_center_id,
        cost_center_name=row.cost_center_name,
        customer_id=transaction.customer_id,
        customer_name=row.customer_name,
        lawsuit_id=transaction.lawsuit_id,
        description=transaction.description,
        amount=transaction.amount,
        due_date=transaction.due_date,
        payment_date=transaction.payment_date,
        competence=transaction.competence,
        created_at=transaction.created_at,
        series_id=transaction.series_id,
        installment_number=transaction.installment_number,
        is_internal=transaction.is_internal,
        internal_note=transaction.internal_note,
    )


def _totals_of(items: list[TransactionResponse]) -> TransactionTotalsResponse:
    """Totais de um conjunto já pequeno e em memória (série tem no máx. 100 parcelas,
    spec 057) — não uma listagem paginada, então soma em Python é aceitável aqui
    (a auditoria numérica de 060 é sobre a UI nunca calcular, não sobre o backend)."""
    total = sum((item.amount for item in items), Decimal(0))
    balance = sum(
        (
            item.amount if item.kind == TransactionKind.RECEITA else -item.amount
            for item in items
            if item.kind != TransactionKind.TRANSFERENCIA
        ),
        Decimal(0),
    )
    expected = sum((item.amount for item in items if item.payment_date is None), Decimal(0))
    return TransactionTotalsResponse(total=total, balance=balance, expected=expected)


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
    except FinancialCategoryInUseError as exc:
        raise HTTPException(
            status_code=409,
            detail="Categoria tem lançamentos vinculados — transfira-os antes de excluir.",
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
    except CostCenterInUseError as exc:
        raise HTTPException(
            status_code=409,
            detail="Centro de custo tem lançamentos vinculados — transfira-os antes de excluir.",
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


@router.get("/bank-accounts/balances")
async def list_bank_account_balances(
    account_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(require_financial(FinancialAccess.READ_ONLY)),
    session: AsyncSession = Depends(get_session_for_current_user),
    clock: Clock = Depends(get_clock),
) -> BankAccountBalancesResponse:
    """Spec 059, regra 6/7: saldo real (view materializada) por conta; cartão de
    crédito devolve a fatura do ciclo em vez de saldo (`is_invoice=True`)."""
    rows = await get_account_balances(session, account_id=account_id, today=clock.today())
    return BankAccountBalancesResponse(
        items=[
            AccountBalanceItem(
                account_id=row.account.id,
                name=row.account.name,
                kind=row.account.kind,
                balance=row.balance,
                is_invoice=row.is_invoice,
            )
            for row in rows
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
    except InitialAmountLockedError as exc:
        raise HTTPException(
            status_code=409,
            detail="Saldo inicial não pode mudar depois do primeiro lançamento da conta.",
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
    try:
        await service.delete(account)
    except BankAccountInUseError as exc:
        raise HTTPException(
            status_code=409,
            detail="Conta tem lançamentos vinculados e não pode ser excluída.",
        ) from exc


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
    clock: Clock = Depends(get_clock),
) -> AccountBalanceResponse:
    """Regras 3/4 (spec 055) ainda devolvem só o saldo inicial — completar com os
    lançamentos reais (spec 056) ficou pra um refactor futuro, ver
    docs/DIVIDA-TECNICA.md e Descobertas da spec 056."""
    service = BankAccountService(session=session, tenant_id=current_user.tenant_id)
    account, _ = await get_or_404(lambda: service.get(account_id), "Conta não encontrada.")
    balance = await service.get_balance(account, at=at, today=clock.today())
    return AccountBalanceResponse(
        account_id=account.id, kind=account.kind, balance=balance, as_of=at or clock.today()
    )


# Erro de domínio → mensagem do 422. Tabela em vez de cadeia de `isinstance` (spec 106):
# erro novo é uma linha aqui, e a mensagem fica ao lado do tipo que a produz.
# `TransactionLawsuitNotFoundError` não entra: é o fallback, e deixá-lo explícito na tabela
# esconderia que ele também atende qualquer erro inesperado da família.
_MENSAGEM_POR_ERRO: dict[type[Exception], str] = {
    FuturePaymentDateError: "Data de pagamento não pode ser no futuro.",
    TransactionCategoryNotFoundError: "Categoria não encontrada.",
    TransactionCostCenterNotFoundError: "Centro de custo não encontrado.",
    TransactionAccountNotFoundError: "Conta não encontrada.",
    TransactionCustomerNotFoundError: "Cliente não encontrado.",
}


def _handle_transaction_errors(exc: Exception) -> HTTPException:
    # O mismatch de tipo é o único que compõe a mensagem com dado do próprio erro.
    if isinstance(exc, TransactionCategoryTypeMismatchError):
        return HTTPException(
            status_code=422,
            detail=(
                f"A categoria escolhida é do tipo {exc.category_type}, "
                "incompatível com o lançamento."
            ),
        )
    mensagem = _MENSAGEM_POR_ERRO.get(type(exc), "Processo não encontrado.")
    return HTTPException(status_code=422, detail=mensagem)


_TRANSACTION_VALIDATION_ERRORS = (
    FuturePaymentDateError,
    TransactionCategoryNotFoundError,
    TransactionCategoryTypeMismatchError,
    TransactionCostCenterNotFoundError,
    TransactionAccountNotFoundError,
    TransactionCustomerNotFoundError,
    TransactionLawsuitNotFoundError,
)


@router.get("/transactions")
async def list_transactions(
    kind: TransactionKind | None = Query(default=None),
    customer_id: uuid.UUID | None = Query(default=None),
    lawsuit_id: uuid.UUID | None = Query(default=None),
    status_: Literal["paid", "open"] | None = Query(default=None, alias="status"),
    due_from: date | None = Query(default=None),
    due_to: date | None = Query(default=None),
    q: str | None = Query(default=None),
    internal: Literal["true", "false", "all"] = Query(default="all"),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=100),
    current_user: User = Depends(require_financial(FinancialAccess.READ_ONLY)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> TransactionListResponse:
    service = TransactionService(session=session, tenant_id=current_user.tenant_id)
    internal_filter = None if internal == "all" else internal
    # Spec 098, regra 3: a rota devolvia TODOS os lançamentos do escritório, sem limite
    # nenhum. O contrato de listagem do CLAUDE.md §6 já previa o `next_cursor` — o
    # schema tinha o campo desde a 056, sempre nulo.
    rows, next_cursor = await service.list_transactions(
        kind=kind,
        customer_id=customer_id,
        lawsuit_id=lawsuit_id,
        status=status_,
        due_from=due_from,
        due_to=due_to,
        q=q,
        internal=internal_filter,
        cursor=cursor,
        limit=limit,
    )
    totals = await service.totals(
        kind=kind,
        customer_id=customer_id,
        lawsuit_id=lawsuit_id,
        status=status_,
        due_from=due_from,
        due_to=due_to,
        q=q,
        internal=internal_filter,
    )
    return TransactionListResponse(
        items=[_transaction_to_response(row) for row in rows],
        next_cursor=next_cursor,
        # O total do FILTRO (não o da página) vem junto dos somatórios do rodapé.
        total=totals.count,
        totals=TransactionTotalsResponse(
            total=totals.total, balance=totals.balance, expected=totals.expected
        ),
    )


@router.get("/transactions/stats")
async def get_transaction_stats(
    month: str | None = Query(default=None),
    regime: Regime = Query(default="due"),
    account_id: uuid.UUID | None = Query(default=None),
    _current_user: User = Depends(require_financial(FinancialAccess.READ_ONLY)),
    session: AsyncSession = Depends(get_session_for_current_user),
    clock: Clock = Depends(get_clock),
) -> TransactionStatsResponse:
    reference = parse_month_query(month, clock.today())
    stats = await get_dashboard_stats(
        session, regime=regime, month=reference, account_id=account_id, today=clock.today()
    )
    return TransactionStatsResponse(
        balance=stats.balance,
        balance_previous=stats.balance_previous,
        income_expected=stats.income_expected,
        income_realized=stats.income_realized,
        expense_expected=stats.expense_expected,
        expense_realized=stats.expense_realized,
        overdue=stats.overdue,
        balance_staleness_hint=stats.balance_staleness_hint,
    )


@router.get("/transactions/chart")
async def get_transaction_chart(
    month: str | None = Query(default=None),
    group_by: ChartGroupBy = Query(default="day"),
    account_id: uuid.UUID | None = Query(default=None),
    _current_user: User = Depends(require_financial(FinancialAccess.READ_ONLY)),
    session: AsyncSession = Depends(get_session_for_current_user),
    clock: Clock = Depends(get_clock),
) -> TransactionChartResponse:
    """ADVBOX: gráfico "Receitas x Despesas por vencimento"."""
    reference = parse_month_query(month, clock.today())
    points = await get_chart_series(
        session, month=reference, group_by=group_by, account_id=account_id
    )
    return TransactionChartResponse(
        items=[
            ChartPointResponse(
                period_start=point.period_start, income=point.income, expense=point.expense
            )
            for point in points
        ]
    )


@router.get("/transactions/cash-flow")
async def get_transaction_cash_flow(
    from_: date = Query(alias="from"),
    to: date = Query(),
    account_id: uuid.UUID | None = Query(default=None),
    _current_user: User = Depends(require_financial(FinancialAccess.READ_ONLY)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> CashFlowResponse:
    if to < from_:
        raise HTTPException(status_code=422, detail="'to' precisa ser igual ou posterior a 'from'.")
    points = await get_cash_flow_series(session, start=from_, end=to, account_id=account_id)
    return CashFlowResponse(
        items=[
            CashFlowPointResponse(
                day=point.day, income=point.income, expense=point.expense, balance=point.balance
            )
            for point in points
        ]
    )


@router.post("/transactions", status_code=201)
async def create_transaction(
    payload: TransactionCreateRequest,
    current_user: User = Depends(require_financial(FinancialAccess.FULL)),
    session: AsyncSession = Depends(get_session_for_current_user),
    clock: Clock = Depends(get_clock),
) -> TransactionResponse:
    service = TransactionService(session=session, tenant_id=current_user.tenant_id)
    try:
        row = await service.create(payload, current_user, today=clock.today())
    except _TRANSACTION_VALIDATION_ERRORS as exc:
        raise _handle_transaction_errors(exc) from exc
    return _transaction_to_response(row)


@router.put("/transactions/{transaction_id}")
async def update_transaction(
    transaction_id: uuid.UUID,
    payload: TransactionUpdateRequest,
    current_user: User = Depends(require_financial(FinancialAccess.FULL)),
    session: AsyncSession = Depends(get_session_for_current_user),
    clock: Clock = Depends(get_clock),
) -> TransactionResponse:
    service = TransactionService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(lambda: service.get(transaction_id), "Lançamento não encontrado.")
    try:
        row = await service.update(detail.transaction, payload, current_user, today=clock.today())
    except _TRANSACTION_VALIDATION_ERRORS as exc:
        raise _handle_transaction_errors(exc) from exc
    except PaidTransactionCannotBecomeInternalError as exc:
        raise HTTPException(
            status_code=409, detail="Lançamento pago não pode virar interno — estorne antes."
        ) from exc
    return _transaction_to_response(row)


@router.delete("/transactions/{transaction_id}", status_code=204)
async def delete_transaction(
    transaction_id: uuid.UUID,
    current_user: User = Depends(require_financial(FinancialAccess.FULL)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> None:
    service = TransactionService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(lambda: service.get(transaction_id), "Lançamento não encontrado.")
    try:
        await service.delete(detail.transaction)
    except PaidTransactionNotDeletableError as exc:
        raise HTTPException(
            status_code=409, detail="Lançamento pago — estorne antes de excluir."
        ) from exc
    # Regra 8 (spec 058): excluir lançamento remove os anexos dele.
    attachments = AttachmentService(
        session=session, storage=storage, tenant_id=current_user.tenant_id
    )
    await attachments.remove_all_for("transaction", transaction_id)


@router.post("/transactions/{transaction_id}/pay")
async def pay_transaction(
    transaction_id: uuid.UUID,
    payload: PayTransactionRequest,
    current_user: User = Depends(require_financial(FinancialAccess.FULL)),
    session: AsyncSession = Depends(get_session_for_current_user),
    clock: Clock = Depends(get_clock),
) -> TransactionResponse:
    service = TransactionService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(lambda: service.get(transaction_id), "Lançamento não encontrado.")
    if payload.payment_date > clock.today():
        raise HTTPException(status_code=422, detail="Data de pagamento não pode ser no futuro.")
    await service.pay(detail.transaction, payload.payment_date)
    # Spec 059, regra 11 + spec 078, regra 5: baixa agenda o refresh imediato das
    # views invalidadas por transaction.paid (saldo diário, ciclos e custos de BI).
    schedule_aggregate_refresh("transaction.paid")
    updated = await service.get(transaction_id)
    assert updated is not None
    return _transaction_to_response(updated)


@router.post("/transactions/{transaction_id}/unpay")
async def unpay_transaction(
    transaction_id: uuid.UUID,
    current_user: User = Depends(require_financial(FinancialAccess.FULL)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> TransactionResponse:
    service = TransactionService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(lambda: service.get(transaction_id), "Lançamento não encontrado.")
    await service.unpay(detail.transaction)
    # Estorno muda o saldo do mesmo jeito — mesmo conjunto de views do evento
    # transaction.paid (spec 078, regra 5; mesma motivação da regra 11 da spec 059).
    schedule_aggregate_refresh("transaction.paid")
    updated = await service.get(transaction_id)
    assert updated is not None
    return _transaction_to_response(updated)


def _series_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Série não encontrada.")


def _series_to_response(series: TransactionSeries) -> TransactionSeriesResponse:
    return TransactionSeriesResponse(
        id=series.id,
        is_installment=series.is_installment,
        recurrence=series.recurrence,
        total_installments=series.total_installments,
        until_date=series.until_date,
        generated_until=series.generated_until,
        is_active=series.is_active,
        created_at=series.created_at,
    )


@router.get("/transactions/{transaction_id}/series-preview")
async def get_series_preview(
    transaction_id: uuid.UUID,
    current_user: User = Depends(require_financial(FinancialAccess.READ_ONLY)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> SeriesPreviewResponse:
    transaction_service = TransactionService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(
        lambda: transaction_service.get(transaction_id), "Lançamento não encontrado."
    )
    if detail.transaction.series_id is None:
        return SeriesPreviewResponse(items=[])
    series_service = TransactionSeriesService(session=session, tenant_id=current_user.tenant_id)
    items = await series_service.preview(detail.transaction.series_id)
    return SeriesPreviewResponse(
        items=[
            SeriesPreviewItem(
                id=item.id,
                installment_number=item.installment_number,
                due_date=item.due_date,
                amount=item.amount,
                payment_date=item.payment_date,
            )
            for item in items
        ]
    )


@router.get("/transaction-series/{series_id}")
async def get_transaction_series(
    series_id: uuid.UUID,
    current_user: User = Depends(require_financial(FinancialAccess.READ_ONLY)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> TransactionSeriesResponse:
    service = TransactionSeriesService(session=session, tenant_id=current_user.tenant_id)
    series = await service.get(series_id)
    if series is None:
        raise _series_not_found()
    return _series_to_response(series)


@router.put("/transaction-series/{series_id}")
async def update_transaction_series(
    series_id: uuid.UUID,
    payload: TransactionSeriesUpdateRequest,
    scope: Literal["future", "all"] = Query(default="future"),
    current_user: User = Depends(require_financial(FinancialAccess.FULL)),
    session: AsyncSession = Depends(get_session_for_current_user),
    clock: Clock = Depends(get_clock),
) -> TransactionListResponse:
    service = TransactionSeriesService(session=session, tenant_id=current_user.tenant_id)
    series = await service.get(series_id)
    if series is None:
        raise _series_not_found()
    try:
        updated = await service.update_series(series, payload, scope, today=clock.today())
    except (TransactionCategoryNotFoundError, TransactionCategoryTypeMismatchError) as exc:
        raise _handle_transaction_errors(exc) from exc
    detail_repo = TransactionService(session=session, tenant_id=current_user.tenant_id)
    rows = [await detail_repo.get(transaction.id) for transaction in updated]
    items = [_transaction_to_response(row) for row in rows if row is not None]
    return TransactionListResponse(items=items, total=len(items), totals=_totals_of(items))


@router.delete("/transaction-series/{series_id}", status_code=204)
async def delete_transaction_series(
    series_id: uuid.UUID,
    scope: Literal["future", "all"] = Query(default="future"),
    current_user: User = Depends(require_financial(FinancialAccess.FULL)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    service = TransactionSeriesService(session=session, tenant_id=current_user.tenant_id)
    series = await service.get(series_id)
    if series is None:
        raise _series_not_found()
    try:
        await service.delete_series(series, scope)
    except SeriesHasPaidTransactionError as exc:
        raise HTTPException(
            status_code=409, detail="Série tem lançamento pago — estorne antes de excluir tudo."
        ) from exc


@router.post("/transactions/{transaction_id}/attachments", status_code=201)
async def upload_transaction_attachment(
    transaction_id: uuid.UUID,
    file: UploadFile,
    current_user: User = Depends(require_financial(FinancialAccess.FULL)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> AttachmentResponse:
    service = AttachmentService(session=session, storage=storage, tenant_id=current_user.tenant_id)
    content = await file.read()
    try:
        attachment = await service.upload(
            current_user,
            attached_to_type="transaction",
            attached_to_id=transaction_id,
            filename=file.filename or "arquivo",
            content_type=file.content_type or "application/octet-stream",
            content=content,
        )
    except AttachmentTooLargeError as exc:
        raise HTTPException(status_code=422, detail="Anexo acima de 50 MB.") from exc
    except AttachmentTypeBlockedError as exc:
        raise HTTPException(status_code=422, detail="Tipo de arquivo não permitido.") from exc
    except TransactionAttachmentLimitError as exc:
        raise HTTPException(
            status_code=422, detail="Limite de 20 anexos por lançamento atingido."
        ) from exc
    except AttachmentTargetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado.") from exc
    return AttachmentResponse(
        id=attachment.id,
        filename=attachment.filename,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        attached_to_type=attachment.attached_to_type,
        attached_to_id=attachment.attached_to_id,
        uploaded_by=attachment.uploaded_by,
        created_at=attachment.created_at,
    )


@router.get("/transactions/{transaction_id}/attachments")
async def list_transaction_attachments(
    transaction_id: uuid.UUID,
    current_user: User = Depends(require_financial(FinancialAccess.READ_ONLY)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> list[AttachmentResponse]:
    service = AttachmentService(session=session, storage=storage, tenant_id=current_user.tenant_id)
    try:
        items = await service.list_for("transaction", transaction_id, current_user)
    except AttachmentTargetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Lançamento não encontrado.") from exc
    return [
        AttachmentResponse(
            id=item.id,
            filename=item.filename,
            content_type=item.content_type,
            size_bytes=item.size_bytes,
            attached_to_type=item.attached_to_type,
            attached_to_id=item.attached_to_id,
            uploaded_by=item.uploaded_by,
            created_at=item.created_at,
        )
        for item in items
    ]


_REPORT_EXPORT_COLUMNS: list[ExportColumn[ReportGroupRow]] = [
    ExportColumn(header="Grupo DRE", value=lambda row: row.dre_group_name),
    ExportColumn(header="Receita", value=lambda row: str(row.receita)),
    ExportColumn(header="Despesa", value=lambda row: str(row.despesa)),
    ExportColumn(header="Total", value=lambda row: str(row.total)),
]


async def _load_report(
    session: AsyncSession,
    *,
    regime: ReportRegime,
    from_: date,
    to: date,
    account_id: uuid.UUID | None,
) -> FinancialReportResponse:
    if to < from_:
        raise HTTPException(status_code=422, detail="'to' precisa ser igual ou posterior a 'from'.")
    report = await get_financial_report(
        session, regime=regime, start=from_, end=to, account_id=account_id
    )
    return FinancialReportResponse(
        period_start=report.period_start,
        period_end=report.period_end,
        rows=[
            ReportGroupRowResponse(
                dre_group_id=row.dre_group_id,
                dre_group_name=row.dre_group_name,
                nature=row.nature,
                receita=row.receita,
                despesa=row.despesa,
                total=row.total,
            )
            for row in report.rows
        ],
        total_receita=report.total_receita,
        total_despesa=report.total_despesa,
        resultado=report.resultado,
    )


@router.get("/financial-reports/dre")
async def get_dre_report(
    from_: date = Query(alias="from"),
    to: date = Query(),
    account_id: uuid.UUID | None = Query(default=None),
    _current_user: User = Depends(require_financial(FinancialAccess.READ_ONLY)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> FinancialReportResponse:
    return await _load_report(session, regime="dre", from_=from_, to=to, account_id=account_id)


@router.get("/financial-reports/dfc")
async def get_dfc_report(
    from_: date = Query(alias="from"),
    to: date = Query(),
    account_id: uuid.UUID | None = Query(default=None),
    _current_user: User = Depends(require_financial(FinancialAccess.READ_ONLY)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> FinancialReportResponse:
    return await _load_report(session, regime="dfc", from_=from_, to=to, account_id=account_id)


@router.post("/financial-reports/export")
async def export_financial_report(
    payload: FinancialReportExportRequest,
    _current_user: User = Depends(require_financial(FinancialAccess.READ_ONLY)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> Response:
    if payload.to < payload.from_:
        raise HTTPException(status_code=422, detail="'to' precisa ser igual ou posterior a 'from'.")
    report = await get_financial_report(
        session,
        regime=payload.report,
        start=payload.from_,
        end=payload.to,
        account_id=payload.account_id,
    )
    export = TableExport(sheet_title=payload.report.upper(), columns=_REPORT_EXPORT_COLUMNS)
    content = export.xlsx(report.rows) if payload.format == "xlsx" else export.pdf(report.rows)
    media_type = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if payload.format == "xlsx"
        else "application/pdf"
    )
    filename = f"{payload.report}.{payload.format}"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
