import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, func, text
from sqlalchemy.dialects.postgresql import ENUM as PGENUM
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin


class TemplateType(StrEnum):
    """Os 4 tipos de modelo do levantamento ADVBOX (docs §4.9)."""

    CONTRATO = "CONTRATO"
    PETICAO = "PETICAO"
    RECURSO = "RECURSO"
    DOCUMENTO = "DOCUMENTO"


class Template(TenantMixin, Base):
    """Modelo de documento (spec 064) — `content` é texto simples por enquanto; o
    editor rico (spec 065) substitui o formato sem precisar de migration nova, a
    coluna já existe. `deleted_at` é a lixeira (regra 3): nunca hard-delete."""

    __tablename__ = "templates"

    name: Mapped[str]
    type: Mapped[TemplateType] = mapped_column(
        PGENUM(TemplateType, name="template_type", create_type=False)
    )
    content: Mapped[str] = mapped_column(default="", server_default=text("''"))
    created_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
