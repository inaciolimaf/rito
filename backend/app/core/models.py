import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    # Toda coluna `Mapped[datetime]` vira TIMESTAMPTZ — sem isso o SQLAlchemy infere
    # DateTime "naive" por padrão, e o asyncpg rejeita datetime com tzinfo contra uma
    # coluna que ele acha que não tem timezone.
    type_annotation_map = {datetime: DateTime(timezone=True)}

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )


class TenantMixin:
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )


class Tenant(Base):
    __tablename__ = "tenants"

    slug: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
