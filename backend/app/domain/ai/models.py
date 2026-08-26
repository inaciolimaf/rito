import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import ForeignKey, Numeric, SmallInteger, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ENUM as PGENUM
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
    # Spec 085, regra 9: modelo escolhido pelo usuário para ESTE thread (nulo = o da
    # configuração da feature). Regra 7: arquivamento por inatividade.
    model: Mapped[str | None] = mapped_column(default=None)
    archived_at: Mapped[datetime | None] = mapped_column(default=None)
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


class AiToolCall(TenantMixin, Base):
    """Uma consulta do agente ao banco (spec 083, regra 6). Guarda o que foi pedido e
    quanto voltou — nunca o conteúdo lido, que já vive protegido na tabela de origem."""

    __tablename__ = "ai_tool_calls"

    thread_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_threads.id", ondelete="CASCADE"), default=None
    )
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    tool_name: Mapped[str]
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB(), default=dict)
    result_summary: Mapped[str | None] = mapped_column(default=None)
    row_count: Mapped[int | None] = mapped_column(default=None)
    duration_ms: Mapped[int | None] = mapped_column(default=None)
    error: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class AiActionStatus(StrEnum):
    """Ciclo de uma proposta de escrita (spec 084 §4)."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"
    EXPIRED = "expired"


class AiAction(TenantMixin, Base):
    """Uma escrita PROPOSTA pela IA, esperando confirmação humana (spec 084, regra 1).

    Enquanto esta linha existe em `pending`, nada foi gravado no domínio — o preview é
    literalmente o que vai acontecer se alguém aprovar.
    """

    __tablename__ = "ai_actions"

    thread_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_threads.id", ondelete="CASCADE"), default=None
    )
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    tool_name: Mapped[str]
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB(), default=dict)
    preview: Mapped[dict[str, Any]] = mapped_column(JSONB(), default=dict)
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB(), default=None)
    # PGENUM com os rótulos literais (e não `SAEnum(AiActionStatus)`): o SQLAlchemy
    # persistiria o NOME do membro ("PENDING"), e os rótulos no banco são minúsculos.
    status: Mapped[str] = mapped_column(
        PGENUM(
            "pending",
            "approved",
            "rejected",
            "executed",
            "failed",
            "expired",
            name="ai_action_status",
            create_type=False,
        ),
        default=AiActionStatus.PENDING.value,
        server_default=text("'pending'"),
    )
    affected_type: Mapped[str | None] = mapped_column(default=None)
    affected_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), default=None)
    rejection_reason: Mapped[str | None] = mapped_column(default=None)
    error: Mapped[str | None] = mapped_column(default=None)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), default=None
    )
    decided_at: Mapped[datetime | None] = mapped_column(default=None)
    executed_at: Mapped[datetime | None] = mapped_column(default=None)
    undone_at: Mapped[datetime | None] = mapped_column(default=None)
    expires_at: Mapped[datetime] = mapped_column(server_default=text("now() + interval '1 hour'"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class AiAuditLog(TenantMixin, Base):
    """O que a IA gravou, com estado antes e depois (spec 084, regra 7).

    Append-only garantido no banco (trigger + REVOKE, migration 084): esta tabela é a
    resposta para "quem mudou isso?" quando a resposta for "a IA, e fulano aprovou".
    """

    __tablename__ = "ai_audit_log"

    action_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("ai_actions.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    tool_name: Mapped[str]
    affected_type: Mapped[str]
    affected_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True))
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB(), default=None)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB(), default=None)
    model: Mapped[str]
    thread_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class AiMessage(TenantMixin, Base):
    """Uma mensagem da conversa com o copiloto (spec 085 §4).

    `content` nulo não é erro: é o tenant que não pediu para guardar o texto (regra 13).
    A linha continua servindo para reconstruir o histórico — quantas trocas houve, quais
    ferramentas foram consultadas, que ações foram propostas.
    """

    __tablename__ = "ai_messages"

    thread_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_threads.id", ondelete="CASCADE")
    )
    role: Mapped[str]
    content: Mapped[str | None] = mapped_column(default=None)
    tool_call_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_tool_calls.id", ondelete="SET NULL"), default=None
    )
    action_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_actions.id", ondelete="SET NULL"), default=None
    )
    # Ver a migration 085: `clock_timestamp()` porque pergunta e resposta nascem na
    # mesma transação e precisam sair na ordem em que aconteceram.
    created_at: Mapped[datetime] = mapped_column(server_default=text("clock_timestamp()"))


class EditorAiAction(TenantMixin, Base):
    """Uma ajuda de escrita dentro do editor (spec 088 §4).

    `accepted` nulo é o estado normal logo depois de gerar: a sugestão está na tela em
    cinza, esperando Tab ou Esc. Ele só vira booleano quando alguém decide — e é essa
    proporção que diz se a feature está ajudando (regra 10).
    """

    __tablename__ = "editor_ai_actions"

    template_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("templates.id", ondelete="CASCADE"), default=None
    )
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    action: Mapped[str]
    instruction: Mapped[str | None] = mapped_column(default=None)
    input_excerpt: Mapped[str]
    output: Mapped[str]
    accepted: Mapped[bool | None] = mapped_column(default=None)
    model: Mapped[str]
    tokens_used: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

