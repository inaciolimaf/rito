import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, model_validator

from app.core.schemas import JsonDecimal
from app.domain.financial.models import AccountKind, EntryType


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
