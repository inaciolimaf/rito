import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin


class Attachment(TenantMixin, Base):
    """Anexo genérico (spec 035): hoje ligado a posts e comentários; contatos e
    financeiro reutilizam a mesma tabela — `attached_to_type`/`attached_to_id` sem
    FK de propósito (a validação do alvo é do service, que conhece os tipos)."""

    __tablename__ = "attachments"
    __table_args__ = (
        # Regra 5: 50 MB também em CHECK (defesa em profundidade além do service).
        CheckConstraint("size_bytes >= 0 AND size_bytes <= 52428800", name="ck_attachments_size"),
    )

    storage_key: Mapped[str]
    filename: Mapped[str]
    content_type: Mapped[str]
    size_bytes: Mapped[int]
    attached_to_type: Mapped[str]
    attached_to_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True))
    uploaded_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
