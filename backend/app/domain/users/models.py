import enum
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Interval, Numeric, SmallInteger, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
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


class Occupation(Base):
    """Cargo (spec 012) — taxonomia global, sem tenant_id: mesma lista de 67 cargos para
    todos os escritórios (levantamento ADVBOX, 67 nomes únicos apesar do rótulo "66")."""

    __tablename__ = "occupations"

    # Base.id é UUID (todo o resto do app usa uuid_generate_v4()); occupations é a única
    # tabela com PK inteira fixa (os 67 cargos, seedados por id sequencial) — SQLAlchemy
    # suporta o override por subclasse, é só o mypy que enxerga incompatibilidade de tipo
    # entre as duas declarações de `id`.
    id: Mapped[int] = mapped_column(  # type: ignore[assignment]
        SmallInteger(), primary_key=True, autoincrement=False
    )
    name: Mapped[str] = mapped_column(unique=True)


class User(TenantMixin, Base):
    """Autenticação (spec 004) + dados de RH/cargo/jornada (spec 012)."""

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

    occupation_id: Mapped[int | None] = mapped_column(
        SmallInteger(), ForeignKey("occupations.id"), default=None
    )
    identification: Mapped[str | None] = mapped_column(default=None)  # CPF
    document: Mapped[str | None] = mapped_column(default=None)  # RG
    birthdate: Mapped[date | None] = mapped_column(default=None)
    number_ctps: Mapped[str | None] = mapped_column(default=None)
    number_oab: Mapped[str | None] = mapped_column(default=None)  # "NNNNNN/UF"
    cellphone: Mapped[str | None] = mapped_column(default=None)
    phone: Mapped[str | None] = mapped_column(default=None)
    avatar_key: Mapped[str | None] = mapped_column(default=None)
    salary: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), default=None)
    admission_date: Mapped[date | None] = mapped_column(default=None)
    resignation_date: Mapped[date | None] = mapped_column(default=None)
    work_start: Mapped[time | None] = mapped_column(default=None)
    work_interval: Mapped[timedelta | None] = mapped_column(Interval(), default=None)
    work_end: Mapped[time | None] = mapped_column(default=None)
    points_goal: Mapped[int | None] = mapped_column(default=None)
    report_deadline: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    report_deleted: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    is_responsible: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    # Preferências de UI por usuário (spec 026, regra 7) — chave/valor genérico.
    preferences: Mapped[dict[str, object]] = mapped_column(
        JSONB(), default=dict, server_default=text("'{}'::jsonb")
    )

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class UserInvitation(TenantMixin, Base):
    """Convite por e-mail (spec 012, regra 1-2) — o `User` só é criado no aceite; até lá
    só existe este registro (sem FK para um `user_id` que ainda não existe)."""

    __tablename__ = "user_invitations"

    email: Mapped[str] = mapped_column(CITEXT())
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole, name="user_role", create_type=False))
    financial_access: Mapped[FinancialAccess] = mapped_column(
        SAEnum(FinancialAccess, name="financial_access", create_type=False),
        default=FinancialAccess.NONE,
        server_default=FinancialAccess.NONE.value,
    )
    occupation_id: Mapped[int | None] = mapped_column(
        SmallInteger(), ForeignKey("occupations.id"), default=None
    )
    token_hash: Mapped[str] = mapped_column(unique=True)
    expires_at: Mapped[datetime]
    accepted_at: Mapped[datetime | None] = mapped_column(default=None)
    invited_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
