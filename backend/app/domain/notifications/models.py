import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY as PGARRAY
from sqlalchemy.dialects.postgresql import ENUM as PGENUM
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Text

from app.core.models import CRIADO_EM, Base, TenantMixin


class Notification(TenantMixin, Base):
    """Notificação in-app genérica (spec 035): menção agora; assignment, deadline e
    demais tipos chegam com as próximas specs. O roteamento por canal (e-mail/SMS/
    WhatsApp) é da 069 — aqui só existe o registro in-app."""

    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    kind: Mapped[str]
    title: Mapped[str]
    body: Mapped[str | None] = mapped_column(default=None)
    link: Mapped[str | None] = mapped_column(default=None)
    read_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)


class NotificationEvent(StrEnum):
    """Os 3 eventos com gatilho real hoje (spec 069 §3) — "parceiros" do levantamento
    entra quando a spec 079 existir."""

    NOVO_CLIENTE = "NOVO_CLIENTE"
    NOVO_PROCESSO = "NOVO_PROCESSO"
    INTIMACAO = "INTIMACAO"


class NotificationChannelName(StrEnum):
    """Mesmos 3 nomes de `DunningChannel` (spec 061) — canais complementares ao
    in-app, atrás da mesma interface `MessagingChannel`."""

    EMAIL = "EMAIL"
    SMS = "SMS"
    WHATSAPP = "WHATSAPP"


class NotificationRule(TenantMixin, Base):
    """Config por evento (spec 069, regra 1/2) — `responsible_user_id = NULL` é "não
    notificar" explícito; sem linha nenhuma pro evento é "não configurado" (mesmo
    efeito, estados diferentes)."""

    __tablename__ = "notification_rules"
    __table_args__ = (UniqueConstraint("tenant_id", "event", name="uq_notification_rules_event"),)

    event: Mapped[NotificationEvent] = mapped_column(
        PGENUM(NotificationEvent, name="notification_event", create_type=False)
    )
    responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), default=None
    )
    channels: Mapped[list[str]] = mapped_column(
        PGARRAY(Text()), default=list, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)
    updated_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM, onupdate=CRIADO_EM)


class UserNotificationPreference(TenantMixin, Base):
    """Liga/desliga um canal pra si (spec 069, regra 7) — sem registro = habilitado."""

    __tablename__ = "user_notification_preferences"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "user_id", "channel", name="uq_user_notification_preferences"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    channel: Mapped[NotificationChannelName] = mapped_column(
        PGENUM(NotificationChannelName, name="notification_channel", create_type=False)
    )
    enabled: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
