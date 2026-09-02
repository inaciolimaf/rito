import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import CRIADO_EM, Base, TenantMixin


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
    # Spec 044: até onde a captura já chegou — a janela incremental parte daqui
    # (com 1 dia de sobreposição); nula, a primeira execução usa backfill_from.
    last_captured_date: Mapped[date | None]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Spec 049, regras 1-3: zera em todo sucesso; 3 seguidas abrem `alert_id` (um só por
    # termo — nova falha atualiza a mensagem em vez de duplicar).
    consecutive_failures: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    alert_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("integration_alerts.id")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)


class TermSyncRun(Base, TenantMixin):
    """Histórico de execuções de sincronização — DJEN (spec 043, §4) e, desde a
    refatoração 050 (alvo 1), DataJud também: a tabela virou `sync_runs`,
    genérica por `integration`/`term_id`|`lawsuit_id` (exatamente um dos dois).
    A classe continua `TermSyncRun` de propósito — renomeá-la quebraria o import
    usado por 041-049 sem edição (`from ...monitored_terms.models import
    TermSyncRun`); ver Descobertas da 050."""

    __tablename__ = "sync_runs"
    __table_args__ = (
        Index("ix_sync_runs_term", "term_id", "started_at"),
        Index("ix_sync_runs_lawsuit", "lawsuit_id", "started_at"),
        CheckConstraint("num_nonnulls(term_id, lawsuit_id) = 1", name="ck_sync_runs_subject"),
    )

    term_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("monitored_terms.id", ondelete="CASCADE")
    )
    lawsuit_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("lawsuits.id", ondelete="CASCADE")
    )
    integration: Mapped[str] = mapped_column(Text, default="djen", server_default="djen")
    started_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)
    finished_at: Mapped[datetime | None]
    found_count: Mapped[int] = mapped_column(default=0, server_default="0")
    new_count: Mapped[int] = mapped_column(default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
