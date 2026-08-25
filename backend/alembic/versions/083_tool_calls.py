"""registro de chamadas de ferramenta

Revision ID: 083_tool_calls
Revises: 082_langgraph
Create Date: 2026-08-26

Spec 083 §4: `ai_tool_calls` guarda toda consulta que o agente fez ao banco — qual
ferramenta, com quais argumentos, quantas linhas voltaram e quanto demorou.

Isso é auditoria de ACESSO A DADO, não telemetria: se um dia alguém perguntar "o que a
IA olhou do meu cliente?", a resposta está aqui. O resultado em si não é gravado (só um
resumo e a contagem) — persistir o conteúdo lido duplicaria dado sensível fora das
tabelas que já o protegem.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "083_tool_calls"
down_revision: str | None = "082_langgraph"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "ai_tool_calls",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        # Nulo quando a ferramenta roda fora de uma conversa (ex.: automação da 092).
        sa.Column(
            "thread_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_threads.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("arguments", postgresql.JSONB(), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    for statement in enable_rls_statements("ai_tool_calls"):
        op.execute(statement)
    op.execute("CREATE INDEX ix_tool_calls_thread ON ai_tool_calls (thread_id, created_at)")


def downgrade() -> None:
    op.drop_table("ai_tool_calls")
