import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base


class ExternalRequest(Base):
    """Auditoria de chamada HTTP externa (spec 041, §4).

    `tenant_id` é NULO em chamada de sistema (worker sem tenant) — por isso a
    tabela não usa TenantMixin e a política RLS (migration 041) libera a linha
    quando `tenant_id IS NULL` ou bate com o tenant corrente.
    """

    __tablename__ = "external_requests"

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True
    )
    host: Mapped[str] = mapped_column(Text)
    method: Mapped[str] = mapped_column(Text)
    path: Mapped[str] = mapped_column(Text)
    status_code: Mapped[int | None] = mapped_column(SmallInteger)
    duration_ms: Mapped[int | None] = mapped_column()
    attempt: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
