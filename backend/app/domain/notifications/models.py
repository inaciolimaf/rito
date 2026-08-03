import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin


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
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
