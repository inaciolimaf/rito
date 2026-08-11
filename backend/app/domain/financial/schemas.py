import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.core.schemas import JsonDecimal
from app.domain.financial.models import AccountKind, EntryType, TransactionKind


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
        if self.payment_date is not None and self.payment_date > date.today():
            raise ValueError("Data de pagamento não pode ser no futuro.")
        return self


class TransactionCreateRequest(_TransactionMixin):
    user_id: uuid.UUID | None = None


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


class TransactionListResponse(BaseModel):
    items: list[TransactionResponse]
    next_cursor: None = None
    total: int


class PayTransactionRequest(BaseModel):
    payment_date: date = Field(default_factory=date.today)
