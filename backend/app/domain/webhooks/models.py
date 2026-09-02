"""Endpoints e entregas de webhook (spec 093 §4)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, SmallInteger, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import CRIADO_EM, Base, TenantMixin


class WebhookEndpoint(TenantMixin, Base):
    """Um destino configurado pelo escritório.

    `failure_streak` é contador de SEQUÊNCIA, não total: uma entrega bem-sucedida zera.
    Vinte falhas seguidas (regra 10) significam destino morto — vinte falhas espalhadas
    ao longo de um ano significam internet ruim, e desativar por isso seria pior que o
    problema.
    """

    __tablename__ = "webhook_endpoints"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_webhook_endpoints_name"),)

    name: Mapped[str]
    url: Mapped[str]
    # Regra 8: gerado pelo sistema, exibido uma vez, rotacionável.
    secret: Mapped[str]
    headers: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    failure_streak: Mapped[int] = mapped_column(SmallInteger(), default=0, server_default=text("0"))
    disabled_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)


class WebhookDelivery(TenantMixin, Base):
    """Uma tentativa de entrega, com o que foi mandado e o que voltou.

    O payload fica gravado porque o reenvio manual usa o ORIGINAL (regra 11): remontá-lo
    a partir do estado atual mandaria dados diferentes dos do momento do evento, o que
    transformaria "reenviar" em "mandar outra coisa".
    """

    __tablename__ = "webhook_deliveries"

    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("webhook_endpoints.id", ondelete="CASCADE")
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("automation_runs.id", ondelete="SET NULL"), default=None
    )
    event_kind: Mapped[str]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    attempt: Mapped[int] = mapped_column(SmallInteger(), default=1, server_default=text("1"))
    status_code: Mapped[int | None] = mapped_column(SmallInteger(), default=None)
    response_body: Mapped[str | None] = mapped_column(default=None)
    duration_ms: Mapped[int | None] = mapped_column(default=None)
    error: Mapped[str | None] = mapped_column(default=None)
    delivered_at: Mapped[datetime | None] = mapped_column(default=None)
    next_attempt_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)
