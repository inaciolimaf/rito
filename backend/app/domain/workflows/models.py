import uuid
from datetime import date as date_type
from datetime import datetime

from sqlalchemy import ForeignKey, SmallInteger, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import CRIADO_EM, Base, TenantMixin


class Workflow(TenantMixin, Base):
    """Sequência padronizada de tarefas (spec 038) — disparada ao mover o processo
    de etapa ou aplicada manualmente."""

    __tablename__ = "workflows"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_workflows_tenant_name"),)

    name: Mapped[str]
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)


class WorkflowStep(TenantMixin, Base):
    """Uma etapa da sequência (spec 038 §4): tarefa obrigatória (regra 1), responsável
    opcional (NULL = responsável do processo, regra 2) e prazo opcional em dias úteis
    (NULL = sem prazo, regra 4)."""

    __tablename__ = "workflow_steps"
    __table_args__ = (
        UniqueConstraint("workflow_id", "position", name="uq_workflow_steps_position"),
    )

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(SmallInteger())
    task_type_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("task_types.id")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), default=None
    )
    days_offset: Mapped[int | None] = mapped_column(SmallInteger(), default=None)


class Holiday(Base):
    """Feriado nacional (spec 038 §4) — tabela GLOBAL de referência, como courts e
    steps: sem tenant_id e sem RLS, porque feriado não é dado de tenant.

    A PK é a própria data (modelo da spec): o atributo `id` herdado do Base é
    remapeado para a coluna `date`, como Court faz com seu código inteiro."""

    __tablename__ = "holidays"

    # Base.id é UUID; a PK de feriado é a própria DATA — catálogo global, uma linha
    # por dia, e um id sintético só acrescentaria uma chave para ninguém usar.
    id: Mapped[date_type] = mapped_column("date", primary_key=True)  # type: ignore[assignment]
    name: Mapped[str]
    is_national: Mapped[bool] = mapped_column(default=True, server_default=text("true"))

    @property
    def date(self) -> date_type:
        """Alias legível — a coluna `date` está mapeada no atributo `id` (ver acima)."""
        return self.id
