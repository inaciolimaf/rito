import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.core.schemas import JsonDecimal
from app.domain.financial.models import (
    AccountKind,
    EntryType,
    FinancialRecurrence,
    Transaction,
    TransactionKind,
)


@dataclass
class TransactionRow:
    """Lançamento com os nomes das entidades ligadas já resolvidos — o join que a
    listagem devolve, para a tela não fazer N+1 atrás de conta, categoria e cliente.

    Mora aqui, e não em `repository.py`, porque é forma e não query: o router precisava
    do tipo para anotar `_transaction_to_response` e por isso importava a camada de
    dados (spec 118, checagem 2).
    """

    transaction: Transaction
    user_name: str
    debit_account_name: str | None
    credit_account_name: str | None
    category_name: str | None
    cost_center_name: str | None
    customer_name: str | None


class DreGroupResponse(BaseModel):
    id: int
    name: str
    nature: EntryType


class FinancialCategoryCreateRequest(BaseModel):
    name: str
    type: EntryType
    dre_group_id: int


class FinancialCategoryUpdateRequest(BaseModel):
    name: str
    type: EntryType
    dre_group_id: int
    is_active: bool = True


class FinancialCategoryResponse(BaseModel):
    id: uuid.UUID
    name: str
    type: EntryType
    dre_group_id: int
    dre_group_name: str
    is_default: bool
    is_active: bool
    created_at: datetime


class FinancialCategoryListResponse(BaseModel):
    items: list[FinancialCategoryResponse]
    next_cursor: None = None
    total: int


class CostCenterCreateRequest(BaseModel):
    name: str


class CostCenterUpdateRequest(BaseModel):
    name: str
    is_active: bool = True


class CostCenterResponse(BaseModel):
    id: uuid.UUID
    name: str
    is_default: bool
    is_active: bool
    created_at: datetime


class CostCenterListResponse(BaseModel):
    items: list[CostCenterResponse]
    next_cursor: None = None
    total: int


class TransferFinancialCategoriesRequest(BaseModel):
    from_id: uuid.UUID
    to_id: uuid.UUID


class TransferCostCentersRequest(BaseModel):
    from_id: uuid.UUID
    to_id: uuid.UUID


class FinancialInstitutionResponse(BaseModel):
    id: int
    name: str
    compe_code: str | None


class FinancialInstitutionListResponse(BaseModel):
    items: list[FinancialInstitutionResponse]


class _CardCycleMixin(BaseModel):
    kind: AccountKind
    cycle_day: int | None = None
    due_day: int | None = None

    @model_validator(mode="after")
    def _validate_cycle(self) -> "_CardCycleMixin":
        """Regra 1: `CARTAO_CREDITO` exige os dois; os demais tipos não podem tê-los —
        mesma checagem dos 2 CHECK constraints da migration, aqui só pra devolver 422
        antes de ir ao banco (mesmo padrão de `StageCreateRequest._validate_stagnant_days`)."""
        is_card = self.kind is AccountKind.CARTAO_CREDITO
        has_cycle = self.cycle_day is not None and self.due_day is not None
        has_any = self.cycle_day is not None or self.due_day is not None
        if is_card and not has_cycle:
            raise ValueError("Cartão de crédito exige cycle_day e due_day.")
        if not is_card and has_any:
            raise ValueError("Só cartão de crédito tem cycle_day/due_day.")
        if self.cycle_day is not None and not (1 <= self.cycle_day <= 31):
            raise ValueError("cycle_day deve estar entre 1 e 31.")
        if self.due_day is not None and not (1 <= self.due_day <= 31):
            raise ValueError("due_day deve estar entre 1 e 31.")
        return self


class BankAccountCreateRequest(_CardCycleMixin):
    name: str
    institution_id: int | None = None
    agency: str | None = None
    account_number: str | None = None
    initial_amount: Decimal = Decimal("0")
    is_default: bool = False


class BankAccountUpdateRequest(_CardCycleMixin):
    name: str
    institution_id: int | None = None
    agency: str | None = None
    account_number: str | None = None
    initial_amount: Decimal
    is_active: bool = True


class BankAccountResponse(BaseModel):
    id: uuid.UUID
    kind: AccountKind
    name: str
    institution_id: int | None
    institution_name: str | None
    agency: str | None
    account_number: str | None
    cycle_day: int | None
    due_day: int | None
    initial_amount: JsonDecimal
    is_default: bool
    is_active: bool
    created_at: datetime


class BankAccountListResponse(BaseModel):
    items: list[BankAccountResponse]
    next_cursor: None = None
    total: int


class AccountBalanceResponse(BaseModel):
    account_id: uuid.UUID
    kind: AccountKind
    balance: JsonDecimal
    as_of: date


class _TransactionMixin(BaseModel):
    kind: TransactionKind
    debit_account_id: uuid.UUID | None = None
    credit_account_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    cost_center_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    lawsuit_id: uuid.UUID | None = None
    description: str | None = None
    amount: Decimal = Field(gt=0)
    due_date: date
    payment_date: date | None = None
    competence: date | None = None
    is_internal: bool = False
    internal_note: str | None = None

    @model_validator(mode="after")
    def _validate_shape(self) -> "_TransactionMixin":
        """Regras 2/3/7 que dá pra checar sem consultar o banco — a regra 1 (tipo ×
        categoria) precisa buscar a categoria, fica no service (mesmo padrão de
        `FinancialCategoryService._group_name`, que também valida com uma query)."""
        if self.kind is TransactionKind.TRANSFERENCIA:
            if (
                self.debit_account_id is None
                or self.credit_account_id is None
                or self.debit_account_id == self.credit_account_id
            ):
                raise ValueError("Transferência exige conta de origem e destino diferentes.")
            if self.category_id is not None or self.cost_center_id is not None:
                raise ValueError("Transferência não usa categoria nem centro de custo.")
        else:
            if self.category_id is None or self.cost_center_id is None:
                raise ValueError("Categoria e centro de custo são obrigatórios.")
            if self.credit_account_id is not None:
                raise ValueError("credit_account_id é só para transferência.")
        if self.lawsuit_id is not None and self.customer_id is None:
            raise ValueError("Vincular processo exige cliente.")
        # "Data de pagamento no futuro" saiu daqui na spec 114: `model_validator` não
        # tem fuso do escritório, e o futuro de quem está em Rio Branco não é o mesmo de
        # quem está em Lisboa. A regra virou FuturePaymentDateError no service.
        return self


class InstallmentRequest(BaseModel):
    count: int = Field(ge=2, le=100)


class RecurrenceCreateRequest(BaseModel):
    period: FinancialRecurrence
    until_date: date | None = None


class TransactionCreateRequest(_TransactionMixin):
    user_id: uuid.UUID | None = None
    installment: InstallmentRequest | None = None
    recurrence: RecurrenceCreateRequest | None = None

    @model_validator(mode="after")
    def _validate_series(self) -> "TransactionCreateRequest":
        """Regra 057/objetivo: parcelamento e recorrência são coisas diferentes — nunca
        os dois ao mesmo tempo no mesmo lançamento."""
        if self.installment is not None and self.recurrence is not None:
            raise ValueError("Escolha parcelamento ou recorrência, não os dois.")
        return self


class TransactionUpdateRequest(_TransactionMixin):
    user_id: uuid.UUID | None = None


class TransactionResponse(BaseModel):
    id: uuid.UUID
    kind: TransactionKind
    user_id: uuid.UUID
    user_name: str
    debit_account_id: uuid.UUID | None
    debit_account_name: str | None
    credit_account_id: uuid.UUID | None
    credit_account_name: str | None
    category_id: uuid.UUID | None
    category_name: str | None
    cost_center_id: uuid.UUID | None
    cost_center_name: str | None
    customer_id: uuid.UUID | None
    customer_name: str | None
    lawsuit_id: uuid.UUID | None
    description: str | None
    amount: JsonDecimal
    due_date: date
    payment_date: date | None
    competence: date
    created_at: datetime
    series_id: uuid.UUID | None
    installment_number: int | None
    is_internal: bool
    internal_note: str | None


class TransactionTotalsResponse(BaseModel):
    total: JsonDecimal
    balance: JsonDecimal
    expected: JsonDecimal


class TransactionListResponse(BaseModel):
    items: list[TransactionResponse]
    # Spec 098, regra 3: passou a ser preenchido de verdade — a listagem pagina por
    # keyset em `(due_date, id)`. O campo existia desde a 056, sempre nulo.
    next_cursor: str | None = None
    total: int
    totals: TransactionTotalsResponse


class PayTransactionRequest(BaseModel):
    payment_date: date = Field(default_factory=date.today)


class TransactionSeriesResponse(BaseModel):
    id: uuid.UUID
    is_installment: bool
    recurrence: FinancialRecurrence | None
    total_installments: int | None
    until_date: date | None
    generated_until: date | None
    is_active: bool
    created_at: datetime


class TransactionSeriesUpdateRequest(BaseModel):
    """Regra 7 (spec 057): campos omitidos (`None`) não mudam — só o que vier
    preenchido é reescrito nos lançamentos não pagos do escopo escolhido."""

    amount: Decimal | None = Field(default=None, gt=0)
    category_id: uuid.UUID | None = None
    cost_center_id: uuid.UUID | None = None
    description: str | None = None


class SeriesPreviewItem(BaseModel):
    id: uuid.UUID
    installment_number: int | None
    due_date: date
    amount: JsonDecimal
    payment_date: date | None


class SeriesPreviewResponse(BaseModel):
    items: list[SeriesPreviewItem]


class TransactionStatsResponse(BaseModel):
    balance: JsonDecimal
    balance_previous: JsonDecimal
    income_expected: JsonDecimal
    income_realized: JsonDecimal
    expense_expected: JsonDecimal
    expense_realized: JsonDecimal
    overdue: JsonDecimal
    balance_staleness_hint: str


class ChartPointResponse(BaseModel):
    period_start: date
    income: JsonDecimal
    expense: JsonDecimal


class TransactionChartResponse(BaseModel):
    items: list[ChartPointResponse]


class CashFlowPointResponse(BaseModel):
    day: date
    income: JsonDecimal
    expense: JsonDecimal
    balance: JsonDecimal


class CashFlowResponse(BaseModel):
    items: list[CashFlowPointResponse]


class AccountBalanceItem(BaseModel):
    account_id: uuid.UUID
    name: str
    kind: AccountKind
    balance: JsonDecimal
    is_invoice: bool


class BankAccountBalancesResponse(BaseModel):
    items: list[AccountBalanceItem]


class ReportGroupRowResponse(BaseModel):
    dre_group_id: int
    dre_group_name: str
    nature: EntryType
    receita: JsonDecimal
    despesa: JsonDecimal
    total: JsonDecimal


class FinancialReportResponse(BaseModel):
    period_start: date
    period_end: date
    rows: list[ReportGroupRowResponse]
    total_receita: JsonDecimal
    total_despesa: JsonDecimal
    resultado: JsonDecimal


class FinancialReportExportRequest(BaseModel):
    report: Literal["dre", "dfc"]
    from_: date = Field(alias="from")
    to: date
    account_id: uuid.UUID | None = None
    format: Literal["xlsx", "pdf"]

    model_config = {"populate_by_name": True}
