import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.dialects.postgresql import ENUM as PGENUM
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import CRIADO_EM, Base, TenantMixin


class PartnershipStatus(StrEnum):
    PENDENTE = "PENDENTE"
    ATIVA = "ATIVA"
    RECUSADA = "RECUSADA"
    ENCERRADA = "ENCERRADA"


class Partnership(Base):
    """Parceria entre dois escritórios (spec 079). Única tabela do sistema sem
    `tenant_id`: a linha pertence aos DOIS lados (regra 1 — parceria é bilateral e
    simétrica). Por isso a política de RLS é escrita à mão na migration 079, com
    leitura para os dois tenants e escrita só para quem convidou; aceitar e encerrar
    tocam a linha do outro lado e passam pelas funções `partnership_accept`/
    `partnership_end` (SECURITY DEFINER)."""

    __tablename__ = "partnerships"
    __table_args__ = (
        UniqueConstraint("requester_tenant_id", "invited_email", name="uq_partnership_invite"),
    )

    requester_tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id")
    )
    # Nulo até o aceite (regra 2): o convite existe antes de saber qual é o outro escritório.
    partner_tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), default=None
    )
    invited_email: Mapped[str] = mapped_column(CITEXT())
    status: Mapped[PartnershipStatus] = mapped_column(
        PGENUM(PartnershipStatus, name="partnership_status", create_type=False),
        default=PartnershipStatus.PENDENTE,
        server_default=PartnershipStatus.PENDENTE.value,
    )
    # Zerado no aceite — o convite é de uso único.
    token_hash: Mapped[str | None] = mapped_column(unique=True, default=None)
    invited_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    accepted_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)


class SharedLawsuit(Base):
    """Compartilhamento de UM processo com UM parceiro (regra 3 — nunca a carteira
    inteira). `can_view_financial`/`can_create_tasks` são o escopo explícito que o
    diálogo mostra antes de confirmar."""

    __tablename__ = "shared_lawsuits"
    __table_args__ = (
        UniqueConstraint("lawsuit_id", "partner_tenant_id", name="uq_shared_lawsuit_partner"),
    )

    partnership_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("partnerships.id", ondelete="CASCADE")
    )
    owner_tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id")
    )
    partner_tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id")
    )
    lawsuit_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("lawsuits.id", ondelete="CASCADE")
    )
    can_view_financial: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    can_create_tasks: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    shared_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    # Regra 6: revogar corta o acesso na hora; a linha fica como histórico e o que o
    # parceiro criou permanece.
    revoked_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)


class PartnershipAuditLog(TenantMixin, Base):
    """Regra 11: toda ação de compartilhamento é auditada. Tabela de domínio comum
    (RLS por tenant) — cada lado guarda o registro das próprias ações."""

    __tablename__ = "partnership_audit_logs"

    partnership_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("partnerships.id", ondelete="CASCADE"), default=None
    )
    lawsuit_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), default=None)
    action: Mapped[str] = mapped_column()
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), default=None
    )
    detail: Mapped[dict[str, object]] = mapped_column(
        JSONB(), default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)
