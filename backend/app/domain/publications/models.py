import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin


class Publication(Base, TenantMixin):
    """Comunicação capturada do DJEN (spec 042, §4).

    `availability_date` é a base legal da contagem de prazo (regra 3) — nunca
    `created_at`. `raw_payload` guarda o item inteiro da API (regra 5) para
    reprocessamento sem rebater no DJEN.
    """

    __tablename__ = "publications"
    __table_args__ = (
        UniqueConstraint("tenant_id", "hash", name="uq_publications_tenant_hash"),
        Index(
            "ix_pub_process",
            "tenant_id",
            "process_number",
            postgresql_where=("process_number IS NOT NULL"),
        ),
        Index("ix_pub_lawsuit", "lawsuit_id", postgresql_where=("lawsuit_id IS NOT NULL")),
        Index(
            "ix_pub_unlinked",
            "tenant_id",
            "availability_date",
            postgresql_where=("lawsuit_id IS NULL"),
        ),
        Index(
            "ix_pub_unprocessed",
            "tenant_id",
            "created_at",
            postgresql_where=("processed_at IS NULL"),
        ),
    )

    external_id: Mapped[int] = mapped_column()
    hash: Mapped[str]
    availability_date: Mapped[date]
    court_code: Mapped[str] = mapped_column(Text)
    communication_type: Mapped[str | None] = mapped_column(Text)
    document_type: Mapped[str | None] = mapped_column(Text)
    organ_name: Mapped[str | None] = mapped_column(Text)
    organ_id: Mapped[int | None] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text)
    process_number: Mapped[str | None] = mapped_column(Text)
    medium: Mapped[str | None] = mapped_column(Text)
    medium_full: Mapped[str | None] = mapped_column(Text)
    class_name: Mapped[str | None] = mapped_column(Text)
    class_code: Mapped[int | None] = mapped_column(Integer)
    communication_number: Mapped[int | None] = mapped_column(Integer)
    link: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    cancelled_at: Mapped[date | None]
    lawsuit_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("lawsuits.id")
    )
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB)  # Any: item bruto do DJEN
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # Roteamento (spec 045, §5). `matched_by`: 'process_number' | 'lawyer_id' | 'ambiguous' |
    # 'manual' | null. `routed_by`: 'action_group' | 'term_user' | 'general' |
    # 'gestor_fallback' | null — as 4 rotas em cascata da regra do roteamento.
    post_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("posts.id"))
    matched_by: Mapped[str | None] = mapped_column(Text)
    routed_to: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id")
    )
    routed_by: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None]


class PublicationRecipient(Base, TenantMixin):
    __tablename__ = "publication_recipients"

    publication_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("publications.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(Text)
    pole: Mapped[str | None] = mapped_column(Text)  # 'P' | 'A'


class PublicationLawyer(Base, TenantMixin):
    __tablename__ = "publication_lawyers"
    __table_args__ = (Index("ix_pub_lawyers_ext", "tenant_id", "external_lawyer_id"),)

    publication_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("publications.id", ondelete="CASCADE")
    )
    external_lawyer_id: Mapped[int | None] = mapped_column()
    name: Mapped[str | None] = mapped_column(Text)
    oab_number: Mapped[str | None] = mapped_column(Text)
    oab_state: Mapped[str | None] = mapped_column(String(2))


class PublicationRead(Base, TenantMixin):
    """Leitura por usuário (spec 048, regra 5) — o que um advogado leu não marca
    como lida pros outros. PK surrogate + UNIQUE(publication_id, user_id), mesmo
    padrão de `post_users` (spec 032) em vez da PK composta do §4 original."""

    __tablename__ = "publication_reads"
    __table_args__ = (
        UniqueConstraint("publication_id", "user_id", name="uq_publication_reads_pub_user"),
    )

    publication_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("publications.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    read_at: Mapped[datetime] = mapped_column(server_default=func.now())
