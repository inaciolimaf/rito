from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, SmallInteger, text
from sqlalchemy.dialects.postgresql import ENUM as PGENUM
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import CRIADO_EM, Base, TenantMixin


class TaskComplexity(StrEnum):
    """Complexidade da tarefa (spec 031 §4) — a ordem de declaração é a linha da matriz
    de pontuação (score.py), não altere sem ajustar a matriz."""

    SIMPLES = "SIMPLES"
    MEDIA = "MEDIA"
    MEDIA_ALTA = "MEDIA_ALTA"
    ALTA = "ALTA"
    ALTISSIMA = "ALTISSIMA"


class TaskDuration(StrEnum):
    """Tempo médio estimado (spec 031 §4) — a ordem é a coluna da matriz."""

    MIN_8 = "MIN_8"
    MIN_15 = "MIN_15"
    MIN_30 = "MIN_30"
    HOUR_1 = "HOUR_1"
    HOUR_2_PLUS = "HOUR_2_PLUS"


class TaskType(TenantMixin, Base):
    """Tipo de tarefa do catálogo (spec 031): o que vale pontos no Taskscore.

    `step_id` NULL = tarefa disponível em todas as fases (regra 3). `is_system` marca
    as 3 sistêmicas protegidas (regra 4: não exclui nem renomeia, só a pontuação muda).
    `complexity`/`duration` alimentam a sugestão da matriz — NULL até o gestor
    classificar (o levantamento não tem essa informação por tarefa)."""

    __tablename__ = "task_types"

    step_id: Mapped[int | None] = mapped_column(
        SmallInteger(), ForeignKey("steps.id"), default=None
    )
    name: Mapped[str]
    complexity: Mapped[TaskComplexity | None] = mapped_column(
        PGENUM(TaskComplexity, name="task_complexity", create_type=False), default=None
    )
    duration: Mapped[TaskDuration | None] = mapped_column(
        PGENUM(TaskDuration, name="task_duration", create_type=False), default=None
    )
    # Regra 8: reward ≥ 0 e zero é válido (tarefa que não pontua).
    reward: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    show_in_schedule: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    is_system: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)
