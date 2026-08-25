import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin


class AiFeatureConfig(TenantMixin, Base):
    """Modelo por feature (spec 081, regra 2) — é isto que faz "trocar de modelo" ser
    configuração e não deploy. Sem linha aqui, a feature roda com o padrão do ambiente
    (regra 3)."""

    __tablename__ = "ai_feature_config"
    __table_args__ = (UniqueConstraint("tenant_id", "feature_key", name="uq_ai_feature_config"),)

    feature_key: Mapped[str]
    model: Mapped[str]
    fallback_model: Mapped[str | None] = mapped_column(default=None)
    temperature: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), default=Decimal("0.20"), server_default=text("0.20")
    )
    max_tokens: Mapped[int | None] = mapped_column(default=None)
    # Regra 4: desligada, a UI esconde e a API responde 409.
    is_enabled: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    # Regra 13: sem este opt-in, prompt e resposta NÃO são persistidos (LGPD).
    store_prompts: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), default=None
    )
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class AiUsage(TenantMixin, Base):
    """Um registro por chamada de LLM, inclusive as que falharam (regra 6). É a base do
    painel de custo e a única coisa que sobra de uma conversa quando o tenant não pediu
    para guardar conteúdo."""

    __tablename__ = "ai_usage"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), default=None
    )
    feature_key: Mapped[str]
    model: Mapped[str]
    prompt_tokens: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    completion_tokens: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), default=None)
    latency_ms: Mapped[int | None] = mapped_column(default=None)
    status: Mapped[str]
    error: Mapped[str | None] = mapped_column(default=None)
    prompt: Mapped[str | None] = mapped_column(default=None)
    response_text: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
