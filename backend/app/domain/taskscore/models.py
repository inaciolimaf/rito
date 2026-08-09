import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Integer,
    MetaData,
    Table,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin


class ClosureGoal(TenantMixin, Base):
    """Meta mensal de fechamentos por grupo de ação (spec 039 §4). Ausência de linha =
    sem meta configurada (o widget da 028 convida a configurar, regra 6 daquela spec)."""

    __tablename__ = "closure_goals"
    __table_args__ = (
        CheckConstraint("monthly_target >= 0", name="ck_closure_goals_target"),
        UniqueConstraint("tenant_id", "action_group_id", name="uq_closure_goals_group"),
    )

    action_group_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("action_groups.id")
    )
    monthly_target: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


# View barreira sobre a materialized view (migration 039) — o filtro de tenant está na
# definição da view, então a aplicação consulta sem WHERE de tenant (CLAUDE.md §4).
# Tabela Core somente-leitura: nunca entra em create_all/migration, só em SELECTs.
user_monthly_scores = Table(
    "user_monthly_scores_visible",
    MetaData(),
    Column("tenant_id", PGUUID(as_uuid=True)),
    Column("user_id", PGUUID(as_uuid=True)),
    Column("month", Date),
    Column("tasks_completed", Integer),
    Column("points", Integer),
    Column("on_time", Integer),
    Column("late", Integer),
)


@dataclass
class MonthlyScore:
    """Linha tipada da view barreira — devolvida pelo repositório, montada no service."""

    user_id: uuid.UUID
    month: date
    tasks_completed: int
    points: int
    on_time: int
    late: int
