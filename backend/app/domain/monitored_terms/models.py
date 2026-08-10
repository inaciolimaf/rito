import enum
import uuid
from datetime import date, datetime

from sqlalchemy import CHAR, Boolean, ForeignKey, Index, Text, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin


class TermKind(enum.StrEnum):
    OAB = "OAB"
    CPF = "CPF"
    CNPJ = "CNPJ"


class TermStatus(enum.StrEnum):
    PENDENTE = "PENDENTE"
    SINCRONIZANDO = "SINCRONIZANDO"
    ATIVO = "ATIVO"
    FALHA = "FALHA"
    PAUSADO = "PAUSADO"


class MonitoredTerm(Base, TenantMixin):
    """Termo vigiado no DJEN (spec 043, §4). Sem termo cadastrado, não há captura."""

    __tablename__ = "monitored_terms"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "kind",
            "value",
            "oab_state",
            name="uq_monitored_terms_term",
            postgresql_nulls_not_distinct=True,
        ),
        Index(
            "ix_terms_due",
            "next_sync_at",
            postgresql_where=("is_active AND status <> 'PAUSADO'"),
        ),
    )

    kind: Mapped[TermKind] = mapped_column(SAEnum(TermKind, name="term_kind", create_type=False))
    value: Mapped[str] = mapped_column(Text)
    # Sem ForeignKey aqui: states usa outro DeclarativeBase (LocationBase — taxonomia
    # global sem tenant), e FK entre metadatas não resolve no flush do ORM. A
    # constraint existe no banco (migration 043) e o service valida a UF antes.
    oab_state: Mapped[str | None] = mapped_column(CHAR(2))
    label: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    status: Mapped[TermStatus] = mapped_column(
        SAEnum(TermStatus, name="term_status", create_type=False),
        default=TermStatus.PENDENTE,
        server_default="PENDENTE",
    )
    status_message: Mapped[str | None] = mapped_column(Text)
    last_sync_at: Mapped[datetime | None]
    last_success_at: Mapped[datetime | None]
    next_sync_at: Mapped[datetime | None]
    backfill_from: Mapped[date | None]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class TermSyncRun(Base, TenantMixin):
    """Histórico de execuções de sincronização do termo (spec 043, §4)."""

    __tablename__ = "term_sync_runs"
    __table_args__ = (Index("ix_sync_runs_term", "term_id", "started_at"),)

    term_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("monitored_terms.id", ondelete="CASCADE")
    )
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None]
    found_count: Mapped[int] = mapped_column(default=0, server_default="0")
    new_count: Mapped[int] = mapped_column(default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
