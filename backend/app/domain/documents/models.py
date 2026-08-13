import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ENUM as PGENUM
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin


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
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


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
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
