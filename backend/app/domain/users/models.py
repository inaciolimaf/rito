from datetime import datetime

from sqlalchemy import UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin


class User(TenantMixin, Base):
    """Mínimo para autenticação. Campos de RH/cargo chegam na spec 012."""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),)

    email: Mapped[str] = mapped_column(CITEXT())
    password_hash: Mapped[str | None] = mapped_column(default=None)
    name: Mapped[str]
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    last_login_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
