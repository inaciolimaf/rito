import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, SmallInteger, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin


class Step(Base):
    """Fase do processo (spec 015) — taxonomia global e imutável: as mesmas 9 fases para
    todos os escritórios, sem tenant_id, sem CRUD (mesmo padrão de Occupation, spec 012)."""

    __tablename__ = "steps"

    # Base.id é UUID; steps tem PK inteira fixa (as 9 fases, seedadas por id sequencial) —
    # mesma exceção documentada em Occupation (spec 012).
    id: Mapped[int] = mapped_column(  # type: ignore[assignment]
        SmallInteger(), primary_key=True, autoincrement=False
    )
    name: Mapped[str] = mapped_column(unique=True)
    position: Mapped[int] = mapped_column(SmallInteger(), unique=True)


class Stage(TenantMixin, Base):
    __tablename__ = "stages"

    step_id: Mapped[int] = mapped_column(SmallInteger(), ForeignKey("steps.id"))
    name: Mapped[str]
    position: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    enable_stagnant_days: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    stagnant_days: Mapped[int | None] = mapped_column(default=None)
    # FK real criada na spec 038 (ON DELETE SET NULL: excluir o workflow não derruba
    # a etapa — regra 9).
    suggested_workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="SET NULL"),
        default=None,
    )
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
