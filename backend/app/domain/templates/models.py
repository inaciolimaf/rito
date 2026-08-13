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
    """Modelo de documento (spec 064) — `content` guarda o HTML gerado pelo editor
    rico (spec 065, `editor.getHTML()`), não um formato próprio. `header_content`/
    `footer_content`/`watermark_text` são campos do documento fora do corpo editável
    (regra 1 da 065). `deleted_at` é a lixeira (regra 3 da 064): nunca hard-delete."""

    __tablename__ = "templates"

    name: Mapped[str]
    type: Mapped[TemplateType] = mapped_column(
        PGENUM(TemplateType, name="template_type", create_type=False)
    )
    content: Mapped[str] = mapped_column(default="", server_default=text("''"))
    header_content: Mapped[str] = mapped_column(default="", server_default=text("''"))
    footer_content: Mapped[str] = mapped_column(default="", server_default=text("''"))
    watermark_text: Mapped[str | None] = mapped_column(default=None)
    created_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class PublicTemplate(Base):
    """Biblioteca pública de modelos (spec 068) — taxonomia global e imutável, mesmo
    padrão de `Court`/`Occupation`/`Step`: sem `tenant_id`, sem RLS, sem CRUD por
    tenant, seedada uma vez pela migration. "Copiar" (regra 2) cria um `Template`
    comum do tenant — este registro nunca muda depois de seedado."""

    __tablename__ = "public_templates"

    name: Mapped[str]
    type: Mapped[TemplateType] = mapped_column(
        PGENUM(TemplateType, name="template_type", create_type=False)
    )
    content: Mapped[str] = mapped_column(default="", server_default=text("''"))
    header_content: Mapped[str] = mapped_column(default="", server_default=text("''"))
    footer_content: Mapped[str] = mapped_column(default="", server_default=text("''"))
    watermark_text: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
