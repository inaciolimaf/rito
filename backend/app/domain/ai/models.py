import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import ForeignKey, Numeric, SmallInteger, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
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


class ThreadStatus(StrEnum):
    """Ciclo de vida de uma execução de agente (spec 082 §4).

    `PENDING` não estava na spec: separa "thread criado" de "thread rodando" para que
    o cliente possa abrir o SSE ANTES da execução começar e assistir do primeiro passo
    (é o que a 085 vai fazer). Quem chama `POST /threads` sem `autorun` nunca vê este
    estado.
    """

    PENDING = "pending"
    RUNNING = "running"
    WAITING_HUMAN = "waiting_human"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


class AiThread(TenantMixin, Base):
    """Uma execução de agente, do começo ao fim — inclusive as paradas para o humano
    confirmar (regra 2). `state` é o estado corrente do grafo, igual ao do último
    checkpoint; fica aqui materializado para retomar sem uma segunda query."""

    __tablename__ = "ai_threads"

    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    graph_name: Mapped[str]
    feature_key: Mapped[str]
    title: Mapped[str | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(
        default=ThreadStatus.PENDING.value, server_default=text("'pending'")
    )
    context: Mapped[dict[str, Any]] = mapped_column(
        JSONB(), default=dict, server_default=text("'{}'::jsonb")
    )
    state: Mapped[dict[str, Any]] = mapped_column(
        JSONB(), default=dict, server_default=text("'{}'::jsonb")
    )
    pending_action: Mapped[dict[str, Any] | None] = mapped_column(JSONB(), default=None)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB(), default=None)
    error: Mapped[str | None] = mapped_column(default=None)
    step_count: Mapped[int] = mapped_column(SmallInteger(), default=0, server_default=text("0"))
    # Regra 4: espera humana expira em 24 h — este é o relógio.
    waiting_since: Mapped[datetime | None] = mapped_column(default=None)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class AiCheckpoint(TenantMixin, Base):
    """Estado ao fim de um nó (regra 1). Retomar é ler o último e entrar de novo no
    grafo — o roteador de entrada decide de onde continuar."""

    __tablename__ = "ai_checkpoints"
    __table_args__ = (UniqueConstraint("thread_id", "step", name="uq_checkpoint_step"),)

    thread_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_threads.id", ondelete="CASCADE")
    )
    step: Mapped[int] = mapped_column(SmallInteger())
    node: Mapped[str]
    state: Mapped[dict[str, Any]] = mapped_column(JSONB())
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class AiStep(TenantMixin, Base):
    """O que o agente fez, passo a passo (regra 7). É o registro que permite responder
    "por que o sistema fez isso?" meses depois."""

    __tablename__ = "ai_steps"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_threads.id", ondelete="CASCADE")
    )
    step: Mapped[int] = mapped_column(SmallInteger())
    node: Mapped[str]
    kind: Mapped[str]
    input: Mapped[dict[str, Any] | None] = mapped_column(JSONB(), default=None)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB(), default=None)
    duration_ms: Mapped[int | None] = mapped_column(default=None)
    error: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
