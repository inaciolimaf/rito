"""runtime LangGraph — threads, checkpoints e passos

Revision ID: 082_langgraph
Revises: 081_llm_layer
Create Date: 2026-08-26

Spec 082 §4: `ai_threads` (uma execução de agente), `ai_checkpoints` (o estado ao fim
de cada nó — é o que permite retomar sem refazer) e `ai_steps` (o que o agente fez,
passo a passo, com entrada e saída — regra 7: é o que torna a IA auditável).

`state` e `input`/`output` são JSONB legível de propósito, não blob serializado: o
valor de auditoria da 082 depende de alguém conseguir LER o que o agente recebeu e
devolveu, meses depois, sem o código que gravou. Ver Descobertas da spec sobre por que
o checkpointer é nosso e não o `PostgresSaver` do LangGraph.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "082_langgraph"
down_revision: str | None = "081_llm_layer"
branch_labels: str | None = None
depends_on: str | None = None


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )


def _tenant_column() -> sa.Column:
    return sa.Column(
        "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
    )


def _thread_column() -> sa.Column:
    return sa.Column(
        "thread_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("ai_threads.id", ondelete="CASCADE"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "ai_threads",
        _uuid_pk(),
        _tenant_column(),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("graph_name", sa.Text(), nullable=False),
        sa.Column("feature_key", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        # pending | running | waiting_human | done | error | cancelled
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        # Tela, processo e cliente de onde a conversa nasceu (regra 11 da 085).
        sa.Column(
            "context", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        # Estado corrente do grafo — o mesmo do último checkpoint, materializado aqui
        # para retomar sem uma segunda query.
        sa.Column(
            "state", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("pending_action", postgresql.JSONB(), nullable=True),
        sa.Column("output", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("step_count", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("waiting_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    for statement in enable_rls_statements("ai_threads"):
        op.execute(statement)
    op.execute("CREATE INDEX ix_threads_user ON ai_threads (tenant_id, user_id, updated_at DESC)")
    # Regra 4: o job de expiração procura exatamente por isto.
    op.execute(
        "CREATE INDEX ix_threads_waiting ON ai_threads (waiting_since) "
        "WHERE status = 'waiting_human'"
    )

    op.create_table(
        "ai_checkpoints",
        _uuid_pk(),
        _thread_column(),
        _tenant_column(),
        sa.Column("step", sa.SmallInteger(), nullable=False),
        sa.Column("node", sa.Text(), nullable=False),
        sa.Column("state", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("thread_id", "step", name="uq_checkpoint_step"),
    )
    for statement in enable_rls_statements("ai_checkpoints"):
        op.execute(statement)

    op.create_table(
        "ai_steps",
        _uuid_pk(),
        _thread_column(),
        _tenant_column(),
        sa.Column("step", sa.SmallInteger(), nullable=False),
        sa.Column("node", sa.Text(), nullable=False),
        # 'llm' | 'tool' | 'interrupt' | 'end' | 'error'
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("input", postgresql.JSONB(), nullable=True),
        sa.Column("output", postgresql.JSONB(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    for statement in enable_rls_statements("ai_steps"):
        op.execute(statement)
    op.execute("CREATE INDEX ix_steps_thread ON ai_steps (thread_id, step)")


def downgrade() -> None:
    op.drop_table("ai_steps")
    op.drop_table("ai_checkpoints")
    op.drop_table("ai_threads")
