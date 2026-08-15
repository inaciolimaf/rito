import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import Column, Date, Integer, MetaData, Numeric, Table
from sqlalchemy.dialects.postgresql import UUID as PGUUID

# View barreira sobre a matview agility_daily (migration 071) — o filtro de tenant está
# na definição da view, então a aplicação consulta sem WHERE de tenant (CLAUDE.md §4).
# Tabela Core somente-leitura: nunca entra em create_all/migration, só em SELECTs.
agility_daily = Table(
    "agility_daily_visible",
    MetaData(),
    Column("tenant_id", PGUUID(as_uuid=True)),
    Column("user_id", PGUUID(as_uuid=True)),
    Column("day", Date),
    Column("on_time", Integer),
    Column("late", Integer),
    Column("completed_count", Integer),
    Column("sum_days_to_complete", Numeric),
    Column("sum_delay_days", Numeric),
)


@dataclass
class AgilityTotals:
    """Linha agregada da view barreira, somada sobre um intervalo (regra 4: a média é
    calculada aqui, no service, a partir das somas — nunca média de médias diárias)."""

    on_time: int
    late: int
    pending: int
    completed_count: int
    sum_days_to_complete: Decimal
    sum_delay_days: Decimal


@dataclass
class DelayedTaskRow:
    post_id: uuid.UUID
    task_type_name: str
    user_name: str
    lawsuit_folder: str | None
    deadline_date: date
    completed_at_date: date
    delay_days: int


@dataclass
class DelayedUserRow:
    user_id: uuid.UUID
    user_name: str
    late_count: int
    sum_delay_days: Decimal
