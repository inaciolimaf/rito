import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin
from app.domain.courts.models import Court, CourtSystem


class Lawsuit(TenantMixin, Base):
    """Processo — entidade central do sistema (spec 022). Judicial, administrativo,
    consultivo ou de prospecção, diferenciado pela fase (`stage_id` → `step_id`) em que
    está. `action_group_id`/`step_id` são derivados (regra 2) e nunca residem aqui."""

    __tablename__ = "lawsuits"
    __table_args__ = (
        CheckConstraint("folder IS NULL OR length(folder) <= 30", name="ck_lawsuits_folder_length"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    lawsuit_type_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("lawsuit_types.id")
    )
    stage_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("stages.id"))
    # ForeignKey(Court.id)/(CourtSystem.id) em vez de string "courts.id" — `Court`/
    # `CourtSystem` vivem em `CourtBase`, uma `MetaData` própria (spec 021), então a
    # resolução por string (que só busca na `MetaData` da própria tabela, `Base.metadata`)
    # não encontra a tabela alvo; passar a coluna real resolve sem depender de qual
    # `MetaData` cada uma pertence.
    court_id: Mapped[int | None] = mapped_column(SmallInteger(), ForeignKey(Court.id), default=None)
    court_system_id: Mapped[int | None] = mapped_column(
        SmallInteger(), ForeignKey(CourtSystem.id), default=None
    )
    process_number: Mapped[str | None] = mapped_column(default=None)
    protocol_number: Mapped[str | None] = mapped_column(default=None)
    originating_process: Mapped[str | None] = mapped_column(default=None)
    folder: Mapped[str | None] = mapped_column(default=None)
    filing_year: Mapped[int | None] = mapped_column(SmallInteger(), default=None)
    judiciary: Mapped[str | None] = mapped_column(default=None)
    county: Mapped[str | None] = mapped_column(default=None)
    court_division: Mapped[str | None] = mapped_column(default=None)
    process_date: Mapped[date | None] = mapped_column(default=None)
    notes: Mapped[str | None] = mapped_column(default=None)
    is_archived: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
