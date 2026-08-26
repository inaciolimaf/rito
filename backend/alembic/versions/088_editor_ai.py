"""assistência de escrita no editor

Revision ID: 088_editor_ai
Revises: 087_legal_agents
Create Date: 2026-08-26

Spec 088 §4: `editor_ai_actions` registra cada ajuda de escrita — o trecho que entrou,
o que a IA devolveu e se a pessoa aceitou.

`accepted` é o campo que justifica a tabela (regra 10): sem ele, "a IA no editor está
boa?" só teria resposta por opinião. Nulo = ainda não houve gesto; falso = a pessoa
descartou, e descartar muito é o sinal de que o prompt (ou o modelo) precisa mudar.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "088_editor_ai"
down_revision: str | None = "087_legal_agents"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "editor_ai_actions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        # Nulo quando a ajuda acontece fora de um modelo salvo (seleção avulsa).
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("templates.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        # 'continue' | 'rewrite' | 'tone' | 'review' | 'ground'
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=True),
        sa.Column("input_excerpt", sa.Text(), nullable=False),
        sa.Column("output", sa.Text(), nullable=False),
        # Regra 10: nulo até a pessoa aceitar (Tab) ou descartar (Esc).
        sa.Column("accepted", sa.Boolean(), nullable=True),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    for statement in enable_rls_statements("editor_ai_actions"):
        op.execute(statement)
    op.execute(
        "CREATE INDEX ix_editor_ai_template ON editor_ai_actions (template_id, created_at DESC)"
    )


def downgrade() -> None:
    op.drop_table("editor_ai_actions")
