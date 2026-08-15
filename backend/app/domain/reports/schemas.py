import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class AgilityResponse(BaseModel):
    on_time: int
    late: int
    pending: int
    avg_days_to_complete: float | None
    avg_delay_days: float | None
    staleness_hint: str


class DelayedTaskItem(BaseModel):
    post_id: uuid.UUID
    task_type_name: str
    user_name: str
    lawsuit_folder: str | None
    deadline_date: date
    completed_at_date: date
    delay_days: int


class DelayedUserItem(BaseModel):
    user_id: uuid.UUID
    user_name: str
    late_count: int
    avg_delay_days: float


class MostDelayedResponse(BaseModel):
    tasks: list[DelayedTaskItem]
    users: list[DelayedUserItem]


class ProductivityResponse(BaseModel):
    assigned: int
    completed: int
    late: int
    due_in_5_days: int


class WeeklyChartPoint(BaseModel):
    label: str
    day: date
    assigned: int
    completed: int


class WeeklyChartResponse(BaseModel):
    days: list[WeeklyChartPoint]


# ---- relatórios tabulares (spec 072) ----------------------------------------------

ReportKey = Literal[
    "productivity",
    "delayed_tasks",
    "access_logs",
    "new_customers",
    "new_lawsuits",
    "won_lawsuits",
    "lost_lawsuits",
    "hearings",
    "contrary_parties",
]

REPORT_KEYS: tuple[ReportKey, ...] = (
    "productivity",
    "delayed_tasks",
    "access_logs",
    "new_customers",
    "new_lawsuits",
    "won_lawsuits",
    "lost_lawsuits",
    "hearings",
    "contrary_parties",
)


class ProductivityRow(BaseModel):
    post_id: uuid.UUID
    responsible_name: str
    customer_name: str | None
    task_type_name: str
    points: int
    scheduled_date: date | None
    completed_at: datetime | None


class DelayedTaskRowItem(BaseModel):
    post_id: uuid.UUID
    responsible_name: str
    customer_name: str | None
    task_type_name: str
    points: int
    scheduled_date: date | None
    delay_days: int


class AccessLogRow(BaseModel):
    user_id: uuid.UUID
    user_name: str
    day: date
    ip_address: str | None
    first_login: datetime
    last_login: datetime


class NewCustomerRow(BaseModel):
    customer_id: uuid.UUID
    name: str
    contact: str | None
    city_state: str | None
    origin_name: str | None
    created_at: datetime


class NewLawsuitRow(BaseModel):
    lawsuit_id: uuid.UUID
    parties: str
    lawsuit_type_name: str
    process_number: str | None
    responsible_name: str
    created_at: datetime


class LawsuitOutcomeRow(BaseModel):
    lawsuit_id: uuid.UUID
    parties: str
    lawsuit_type_name: str
    process_number: str | None
    fees_value: Decimal | None
    closure_date: date
    total_days: int


class HearingRow(BaseModel):
    post_id: uuid.UUID
    scheduled_date: date
    scheduled_time: time | None
    task_type_name: str
    process_number: str | None
    parties: str
    location: str | None
    responsible_name: str | None


class ContraryPartyRow(BaseModel):
    customer_id: uuid.UUID
    name: str
    identification: str | None
    city: str | None
    lawsuit_count: int


ReportRow = (
    ProductivityRow
    | DelayedTaskRowItem
    | AccessLogRow
    | NewCustomerRow
    | NewLawsuitRow
    | LawsuitOutcomeRow
    | HearingRow
    | ContraryPartyRow
)


class ReportListResponse(BaseModel):
    items: list[ReportRow]
    next_cursor: str | None
    total: int
    # Rodapé de soma de pontos (regra 4: productivity/delayed_tasks) — None nos demais.
    points_total: int | None = None
    # Regra 5: motivo do estado vazio quando o relatório está desligado (access_logs
    # sem o rastreamento ligado, spec 073). None = relatório disponível normalmente.
    disabled_reason: str | None = None
