import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.core.schemas import JsonDecimal
from app.domain.dunning.models import DunningChannel, DunningStatus

_DEFAULT_TEMPLATE = (
    "Olá {{customer_name}}, identificamos um valor de {{amount}} com vencimento em "
    "{{due_date}} ainda em aberto. Por favor, entre em contato para regularizar."
)


class DunningRuleUpsertRequest(BaseModel):
    days_offset: int = Field(ge=-365, le=365)
    channel: DunningChannel
    template: str = Field(min_length=1, default=_DEFAULT_TEMPLATE)
    is_active: bool = True


class DunningRuleResponse(BaseModel):
    id: uuid.UUID
    days_offset: int
    channel: DunningChannel
    template: str
    is_active: bool
    created_at: datetime


class DunningRuleListResponse(BaseModel):
    items: list[DunningRuleResponse]


class OverdueTransactionResponse(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID | None
    customer_name: str | None
    lawsuit_id: uuid.UUID | None
    process_number: str | None
    description: str | None
    amount: JsonDecimal
    due_date: date
    days_overdue: int


class OverdueListResponse(BaseModel):
    items: list[OverdueTransactionResponse]
    next_cursor: str | None
    total: int


class AgingBucketResponse(BaseModel):
    bucket: str
    total: JsonDecimal


class DebtorResponse(BaseModel):
    customer_id: uuid.UUID
    customer_name: str
    total: JsonDecimal


class OverdueSummaryResponse(BaseModel):
    total: JsonDecimal
    by_aging: list[AgingBucketResponse]
    top_debtors: list[DebtorResponse]


class SendDunningRequest(BaseModel):
    channel: DunningChannel
    template: str = Field(min_length=1, default=_DEFAULT_TEMPLATE)


class DunningAttemptResponse(BaseModel):
    id: uuid.UUID
    transaction_id: uuid.UUID
    rule_id: uuid.UUID | None
    is_manual: bool
    channel: DunningChannel
    sent_to: str
    status: DunningStatus
    error: str | None
    sent_at: datetime


class DunningAttemptListResponse(BaseModel):
    items: list[DunningAttemptResponse]
