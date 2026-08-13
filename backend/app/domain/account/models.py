import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, func, text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.dialects.postgresql import ENUM as PGENUM
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin

DEFAULT_TIMEZONE = "America/Sao_Paulo"


class AccountPlan(StrEnum):
    """Os 4 planos do levantamento ADVBOX (docs §4.13) — de onde vem a quota de
    armazenamento da nuvem de documentos (spec 063)."""

    ESSENCIAL = "ESSENCIAL"
    BANCA_JURIDICA = "BANCA_JURIDICA"
    BANCA_MAX = "BANCA_MAX"
    ELITE = "ELITE"


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
    plan: Mapped[AccountPlan] = mapped_column(
        PGENUM(AccountPlan, name="account_plan", create_type=False),
        default=AccountPlan.ESSENCIAL,
        server_default=text("'ESSENCIAL'"),
    )
    # Rota 3 do roteamento de intimações (spec 045, §5) — responsável geral quando o
    # grupo de ação e o termo monitorado não resolvem.
    default_publications_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
