import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, SmallInteger, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ENUM as PGENUM
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin


class DunningChannel(StrEnum):
    """Os 3 canais da régua (spec 061 §4) — só EMAIL tem provider real; SMS e WHATSAPP
    ficam atrás de `MessagingChannel` sem provider (regra 9, §3 fora de escopo)."""

    EMAIL = "EMAIL"
    SMS = "SMS"
    WHATSAPP = "WHATSAPP"


class DunningStatus(StrEnum):
    """Resultado de uma tentativa (regra 5/9: silêncio nunca — sempre grava algo)."""

    SENT = "SENT"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class DunningRule(TenantMixin, Base):
    """Régua de cobrança (spec 061 §4) — `days_offset` relativo ao vencimento do
    lançamento (regra 3): negativo dispara ANTES (lembrete), positivo DEPOIS (cobrança).
    `UNIQUE(tenant_id, days_offset, channel)` é a regra 4 do lado da REGRA (não pode
    haver duas réguas iguais); a regra 4 do lado da TENTATIVA (não repetir a mesma régua
    no mesmo lançamento) é `uq_dunning_attempts_tx_rule`, na migration."""

    __tablename__ = "dunning_rules"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "days_offset", "channel", name="uq_dunning_rules_offset_channel"
        ),
    )

    days_offset: Mapped[int] = mapped_column(SmallInteger())
    channel: Mapped[DunningChannel] = mapped_column(
        PGENUM(DunningChannel, name="dunning_channel", create_type=False)
    )
    template: Mapped[str]
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class DunningAttempt(TenantMixin, Base):
    """Tentativa de cobrança (spec 061 §4) — uma linha por envio, disparado pela régua
    (`rule_id` preenchido) ou manual (`rule_id` nulo, regra 8: sempre permitido, nunca
    colide com a UNIQUE porque Postgres trata NULL como distinto)."""

    __tablename__ = "dunning_attempts"
    __table_args__ = (
        UniqueConstraint("transaction_id", "rule_id", name="uq_dunning_attempts_tx_rule"),
    )

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE")
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("dunning_rules.id", ondelete="SET NULL"), default=None
    )
    channel: Mapped[DunningChannel] = mapped_column(
        PGENUM(DunningChannel, name="dunning_channel", create_type=False)
    )
    sent_to: Mapped[str]
    status: Mapped[DunningStatus] = mapped_column(
        PGENUM(DunningStatus, name="dunning_status", create_type=False)
    )
    error: Mapped[str | None] = mapped_column(default=None)
    sent_at: Mapped[datetime] = mapped_column(server_default=func.now())
