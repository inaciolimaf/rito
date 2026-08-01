from datetime import datetime

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin

DEFAULT_TIMEZONE = "America/Sao_Paulo"


class Account(TenantMixin, Base):
    """Escritório dono do tenant — 1:1 com `tenants` (spec 011)."""

    __tablename__ = "accounts"

    name: Mapped[str]
    alternate_name: Mapped[str]
    identification: Mapped[str]
    country: Mapped[str] = mapped_column(default="BRASIL", server_default="BRASIL")
    state: Mapped[str]
    city: Mapped[str]
    postal_code: Mapped[str]
    street: Mapped[str]
    region: Mapped[str]
    cellphone: Mapped[str]
    phone: Mapped[str]
    email: Mapped[str] = mapped_column(CITEXT())
    email_admin: Mapped[str] = mapped_column(CITEXT())
    site: Mapped[str | None] = mapped_column(default=None)
    timezone: Mapped[str] = mapped_column(default=DEFAULT_TIMEZONE, server_default=DEFAULT_TIMEZONE)
    logo_key: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
