import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import CRIADO_EM, Base, TenantMixin


class LegalAgent(Base):
    """Agente de petição por área (spec 087 §4).

    `tenant_id` NULO é o agente de sistema — os 19 do catálogo, iguais para todos os
    escritórios. Por isso esta classe NÃO usa `TenantMixin`: a coluna existe, mas é
    opcional, e a política de RLS correspondente está documentada em
    `docs/SEGURANCA-RLS.md`.
    """

    __tablename__ = "legal_agents"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_legal_agents_code"),)

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), default=None
    )
    code: Mapped[str] = mapped_column(Text())
    name: Mapped[str] = mapped_column(Text())
    practice_area: Mapped[str] = mapped_column(Text())
    system_prompt: Mapped[str] = mapped_column(Text())
    # Regra 10: o prompt de fábrica fica preservado para restauração.
    original_system_prompt: Mapped[str] = mapped_column(Text())
    default_template_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("templates.id", ondelete="SET NULL"), default=None
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean(), default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)
    updated_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM, onupdate=CRIADO_EM)


class AgentGeneration(TenantMixin, Base):
    """Uma minuta produzida por um agente (spec 087 §4).

    Existir aqui não significa estar no processo: `saved_template_id` só é preenchido
    quando o usuário mandar salvar (regra 12). Até lá, é rascunho de IA.
    """

    __tablename__ = "agent_generations"

    agent_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("legal_agents.id"))
    lawsuit_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("lawsuits.id", ondelete="CASCADE")
    )
    thread_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_threads.id", ondelete="SET NULL"), default=None
    )
    user_instructions: Mapped[str | None] = mapped_column(Text(), default=None)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB(), default=dict)
    template_used_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("templates.id", ondelete="SET NULL"), default=None
    )
    model: Mapped[str] = mapped_column(Text())
    tokens_used: Mapped[int | None] = mapped_column(Integer(), default=None)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB(), default=list, server_default=text("'[]'::jsonb")
    )
    generated_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    saved_template_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("templates.id", ondelete="SET NULL"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)
