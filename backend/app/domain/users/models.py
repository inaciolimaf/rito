import enum
from datetime import datetime

from sqlalchemy import Enum as SAEnum
from sqlalchemy import UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin


class UserRole(enum.StrEnum):
    GESTOR = "GESTOR"
    ADMINISTRADOR = "ADMINISTRADOR"
    COLABORADOR = "COLABORADOR"


class FinancialAccess(enum.StrEnum):
    NONE = "NONE"
    READ_ONLY = "READ_ONLY"
    FULL = "FULL"


class User(TenantMixin, Base):
    """Mínimo para autenticação. Campos de RH/cargo chegam na spec 012."""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),)

    email: Mapped[str] = mapped_column(CITEXT())
    password_hash: Mapped[str | None] = mapped_column(default=None)
    name: Mapped[str]
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    last_login_at: Mapped[datetime | None] = mapped_column(default=None)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", create_type=False),
        default=UserRole.COLABORADOR,
        server_default=UserRole.COLABORADOR.value,
    )
    financial_access: Mapped[FinancialAccess] = mapped_column(
        SAEnum(FinancialAccess, name="financial_access", create_type=False),
        default=FinancialAccess.NONE,
        server_default=FinancialAccess.NONE.value,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
