import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, SmallInteger, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin


class PublicationAnalysis(TenantMixin, Base):
    """O que a IA leu numa intimação (spec 086 §4).

    Enquanto `reviewed_at` for nulo, tudo aqui é **sugestão** — inclusive (e
    principalmente) o prazo. É a linha entre "a IA ajudou" e "a IA decidiu", e ela é
    verificada em teste.
    """

    __tablename__ = "publication_analyses"

    publication_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("publications.id", ondelete="CASCADE"),
        unique=True,
    )
    summary: Mapped[str] = mapped_column(Text())
    act_type: Mapped[str | None] = mapped_column(Text(), default=None)
    requires_action: Mapped[bool] = mapped_column(
        Boolean(), default=False, server_default=text("false")
    )
    deadline_days: Mapped[int | None] = mapped_column(SmallInteger(), default=None)
    deadline_kind: Mapped[str | None] = mapped_column(Text(), default=None)
    deadline_date: Mapped[date | None] = mapped_column(Date(), default=None)
    deadline_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), default=None)
    suggested_task_type_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("task_types.id"), default=None
    )
    suggested_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), default=None
    )
    reasoning: Mapped[str | None] = mapped_column(Text(), default=None)
    model: Mapped[str] = mapped_column(Text())
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), default=None
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(default=None)
    human_correction: Mapped[dict[str, Any] | None] = mapped_column(JSONB(), default=None)
    previous_corrections: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB(), default=list, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
