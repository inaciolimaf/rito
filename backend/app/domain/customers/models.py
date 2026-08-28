import enum
import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin


class PersonType(enum.StrEnum):
    PF = "PF"
    PJ = "PJ"


class MaritalStatus(Base):
    """Estado civil (spec 017) — taxonomia global e imutável, mesmo padrão de Occupation
    (spec 012) e Step (spec 015): as mesmas 6 opções para todos os escritórios."""

    __tablename__ = "marital_statuses"

    # Base.id é UUID; este é catálogo GLOBAL com PK inteira fixa (seed por id
    # sequencial, sem tenant) — mesma exceção documentada em `Step` e `Occupation`.
    id: Mapped[int] = mapped_column(  # type: ignore[assignment]
        SmallInteger(), primary_key=True, autoincrement=False
    )
    name: Mapped[str] = mapped_column(unique=True)


class Customer(TenantMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint(
            "NOT has_representative OR rep_name IS NOT NULL", name="ck_customers_representative"
        ),
        CheckConstraint("gender IS NULL OR gender IN ('F', 'M')", name="ck_customers_gender"),
    )

    type: Mapped[PersonType] = mapped_column(
        SAEnum(PersonType, name="person_type", create_type=False), default=PersonType.PF
    )
    name: Mapped[str]
    identification: Mapped[str | None] = mapped_column(default=None)
    document: Mapped[str | None] = mapped_column(default=None)
    origin_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customer_origins.id")
    )
    notes: Mapped[str | None] = mapped_column(default=None)
    birthdate: Mapped[date | None] = mapped_column(default=None)
    marital_status_id: Mapped[int | None] = mapped_column(
        ForeignKey("marital_statuses.id"), default=None
    )
    occupation: Mapped[str | None] = mapped_column(default=None)
    gender: Mapped[str | None] = mapped_column(default=None)
    nationality: Mapped[str | None] = mapped_column(default=None)
    mother_name: Mapped[str | None] = mapped_column(default=None)
    cellphone: Mapped[str | None] = mapped_column(default=None)
    phone: Mapped[str | None] = mapped_column(default=None)
    email: Mapped[str | None] = mapped_column(CITEXT(), default=None)
    country: Mapped[str] = mapped_column(default="BRASIL", server_default="BRASIL")
    postal_code: Mapped[str | None] = mapped_column(default=None)
    state: Mapped[str | None] = mapped_column(default=None)
    city: Mapped[str | None] = mapped_column(default=None)
    street: Mapped[str | None] = mapped_column(default=None)
    region: Mapped[str | None] = mapped_column(default=None)
    number_pis: Mapped[str | None] = mapped_column(default=None)
    number_ctps: Mapped[str | None] = mapped_column(default=None)
    number_cid: Mapped[str | None] = mapped_column(default=None)
    photo_key: Mapped[str | None] = mapped_column(default=None)
    has_representative: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    rep_name: Mapped[str | None] = mapped_column(default=None)
    rep_identification: Mapped[str | None] = mapped_column(default=None)
    rep_document: Mapped[str | None] = mapped_column(default=None)
    rep_birthdate: Mapped[date | None] = mapped_column(default=None)
    rep_country: Mapped[str | None] = mapped_column(default=None)
    rep_state: Mapped[str | None] = mapped_column(default=None)
    rep_city: Mapped[str | None] = mapped_column(default=None)
    rep_street: Mapped[str | None] = mapped_column(default=None)
    rep_region: Mapped[str | None] = mapped_column(default=None)
    rep_postal_code: Mapped[str | None] = mapped_column(default=None)
    is_archived: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
