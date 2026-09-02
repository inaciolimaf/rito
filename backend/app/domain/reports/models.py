import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, MetaData, Numeric, Table
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import CRIADO_EM, Base, TenantMixin

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


class AccessLog(TenantMixin, Base):
    """Um registro por login bem-sucedido (spec 073, regra 1 e 3) — refresh de token
    NÃO grava aqui (só `AuthService.login`, nunca `.refresh`, escreve nesta tabela)."""

    __tablename__ = "access_logs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    ip_address: Mapped[str | None] = mapped_column(INET(), default=None)
    user_agent: Mapped[str | None] = mapped_column(default=None)
    occurred_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)


# View barreira sobre a matview timesheet_daily (migration 073) — mesmo padrão de
# agility_daily acima: filtro de tenant embutido na view, sem WHERE manual (CLAUDE.md §4).
timesheet_daily = Table(
    "timesheet_daily_visible",
    MetaData(),
    Column("tenant_id", PGUUID(as_uuid=True)),
    Column("user_id", PGUUID(as_uuid=True)),
    Column("day", Date),
    Column("first_access", DateTime(timezone=True)),
    Column("last_access", DateTime(timezone=True)),
    Column("access_count", Integer),
    Column("last_ip", INET()),
)


@dataclass
class TimesheetDay:
    """Uma célula do livro de ponto — dia sem acesso simplesmente não gera linha
    (regra 7: não presume falta)."""

    day: date
    first_access: datetime | None
    last_access: datetime | None
    access_count: int
    deviation_minutes: int | None  # None = usuário sem jornada cadastrada (regra 6)
    is_weekend: bool
    is_holiday: bool
