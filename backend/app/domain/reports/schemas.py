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


# ---- registro de acesso e livro de ponto (spec 073) --------------------------------


class AccessLogItemResponse(BaseModel):
    log_id: uuid.UUID
    user_name: str
    ip_address: str | None
    occurred_at: datetime


class AccessLogListResponse(BaseModel):
    items: list[AccessLogItemResponse]
    next_cursor: str | None
    total: int


class TimesheetDayResponse(BaseModel):
    day: date
    first_access: datetime | None
    last_access: datetime | None
    access_count: int
    deviation_minutes: int | None
    is_weekend: bool
    is_holiday: bool


class TimesheetResponse(BaseModel):
    user_id: uuid.UUID
    month: date
    days: list[TimesheetDayResponse]


class ReportScopeParams(BaseModel):
    """Os quatro query params que as duas rotas tabulares compartilham (spec 116).

    Simples `BaseModel`, sem `Field(alias=...)`. Motivo medido na spec 116: num modelo
    usado como dependência, o FastAPI monta a assinatura da rota dinamicamente e usa o
    alias como NOME DE PARÂMETRO — o que ele não pode fazer quando o alias é palavra
    reservada do Python. Aí ele silenciosamente cai no nome do campo:

        alias="status" -> query param `status`   (funciona)
        alias="from"   -> query param `from_`    (vira o nome do campo)
        alias="class"  -> query param `a_`       (idem)

    O param `from` é o que o cliente manda desde a spec 070; trocá-lo por `from_` faria a
    filtragem parar sem erro nenhum. O diff de query params desta spec pegou isso — e é
    exatamente o tipo de regressão que um teste de rota que só confere status 200 não vê.

    Por isso quem declara os `Query(...)` é a dependência `report_scope` do router, que os
    mantém exatamente como estavam, e este modelo só carrega os valores para baixo.
    """

    from_: date | None = None
    to: date | None = None
    user_id: uuid.UUID | None = None
    action_group_id: uuid.UUID | None = None
