import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ENUM as PGENUM
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import CRIADO_EM, Base, TenantMixin


class DocumentScopeType(StrEnum):
    """Os 2 escopos da nuvem de documentos (spec 063, docs §4.5/§4.6) — contato e
    processo. Um terceiro escopo (nuvem "geral") ficou fora de escopo (spec 063 §3)."""

    CUSTOMER = "CUSTOMER"
    LAWSUIT = "LAWSUIT"


class DocumentFolder(TenantMixin, Base):
    """Pasta da nuvem de documentos (spec 063) — `scope_id` sem FK de propósito, mesmo
    padrão de `Attachment.attached_to_id` (spec 035): a validação de que o escopo
    existe e pertence ao tenant é do service, que conhece os dois tipos possíveis."""

    __tablename__ = "document_folders"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "scope_type",
            "scope_id",
            "parent_folder_id",
            "name",
            name="uq_document_folders_location_name",
        ),
    )

    scope_type: Mapped[DocumentScopeType] = mapped_column(
        PGENUM(DocumentScopeType, name="document_scope_type", create_type=False)
    )
    scope_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True))
    parent_folder_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("document_folders.id", ondelete="CASCADE"), default=None
    )
    name: Mapped[str]
    created_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)


class Document(TenantMixin, Base):
    """Arquivo da nuvem de documentos (spec 063) — `folder_id` nulo é a raiz do
    escopo. Tamanho e tipo seguem a mesma política de `Attachment` (regra 10): o CHECK
    espelha `AttachmentTooLargeError`/`validate_attachment`, defesa em profundidade."""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0 AND size_bytes <= 52428800", name="ck_documents_size"),
    )

    scope_type: Mapped[DocumentScopeType] = mapped_column(
        PGENUM(DocumentScopeType, name="document_scope_type", create_type=False)
    )
    scope_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True))
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("document_folders.id", ondelete="CASCADE"), default=None
    )
    storage_key: Mapped[str]
    filename: Mapped[str]
    content_type: Mapped[str]
    size_bytes: Mapped[int]
    uploaded_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)


class ExtractionStatus(StrEnum):
    """Estados de uma extração (spec 091 §4). `reviewed` existe entre a revisão e a
    gravação: se a execução falhar no service do domínio, a extração não volta a ser
    `pending` — ela já foi revisada, e o que falhou foi o cadastro."""

    PENDING = "pending"
    REVIEWED = "reviewed"
    APPLIED = "applied"
    DISCARDED = "discarded"


class DocumentExtraction(TenantMixin, Base):
    """Um documento lido e o que se conseguiu tirar dele (spec 091 §4).

    `attachment_id` é nulo no caso mais comum: cadastrar um cliente a partir do RG
    acontece ANTES de existir a ficha à qual anexar o arquivo. O `storage_key` é o que
    sempre existe — o arquivo já está guardado, e é ele que vai para a nuvem do registro
    quando o cadastro for confirmado (regra 7).
    """

    __tablename__ = "document_extractions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'reviewed', 'applied', 'discarded')",
            name="ck_document_extractions_status",
        ),
    )

    attachment_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("attachments.id", ondelete="CASCADE"), default=None
    )
    storage_key: Mapped[str]
    filename: Mapped[str]
    content_type: Mapped[str]
    size_bytes: Mapped[int]
    page_count: Mapped[int | None] = mapped_column(default=None)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    document_kind: Mapped[str | None] = mapped_column(default=None)
    ocr_text: Mapped[str | None] = mapped_column(default=None)
    used_ocr: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    extracted: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    corrections: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    target_type: Mapped[str | None] = mapped_column(default=None)
    action_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_actions.id", ondelete="SET NULL"), default=None
    )
    applied_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), default=None)
    status: Mapped[str] = mapped_column(
        default=ExtractionStatus.PENDING.value, server_default=text("'pending'")
    )
    model: Mapped[str | None] = mapped_column(default=None)
    tokens_used: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)
