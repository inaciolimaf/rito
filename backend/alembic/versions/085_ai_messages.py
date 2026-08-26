"""mensagens do copiloto

Revision ID: 085_ai_messages
Revises: 084_ai_actions
Create Date: 2026-08-26

Spec 085 §4: `ai_messages` é a conversa em si — o que o usuário perguntou, o que o
assistente respondeu e a que consulta ou ação cada resposta se liga.

`content` é NULLABLE de propósito (regra 13 + regra 13 da 081): sem opt-in do tenant, a
linha existe com os metadados (quem, quando, qual ferramenta) e **sem o texto**. O
histórico continua navegável, a conversa não fica gravada.

`ai_threads` ganha duas colunas: `model` (regra 9 — o usuário troca o modelo no painel
e a escolha vale para aquele thread) e `archived_at` (regra 7 — 30 dias sem uso
arquiva, 90 exclui).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "085_ai_messages"
down_revision: str | None = "084_ai_actions"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "ai_messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column(
            "thread_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # 'user' | 'assistant' | 'tool' | 'system'
        sa.Column("role", sa.Text(), nullable=False),
        # Regra 13: nulo quando o tenant não pediu para guardar conteúdo.
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column(
            "tool_call_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_tool_calls.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "action_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_actions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # `clock_timestamp()`, não `now()`: pergunta e resposta são gravadas na MESMA
        # transação, e `now()` devolveria o mesmo instante para as duas — o histórico
        # sairia com a resposta antes da pergunta, dependendo do UUID de desempate.
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
    )
    for statement in enable_rls_statements("ai_messages"):
        op.execute(statement)
    op.execute("CREATE INDEX ix_ai_messages_thread ON ai_messages (thread_id, created_at)")

    op.add_column("ai_threads", sa.Column("model", sa.Text(), nullable=True))
    op.add_column("ai_threads", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_threads", "archived_at")
    op.drop_column("ai_threads", "model")
    op.drop_table("ai_messages")
