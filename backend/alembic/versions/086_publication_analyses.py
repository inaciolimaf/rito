"""análise de intimação por IA

Revision ID: 086_publication_analyses
Revises: 085_ai_messages
Create Date: 2026-08-26

Spec 086 §4: `publication_analyses` guarda o que a IA leu numa intimação — resumo,
tipo de ato, prazo identificado e a data calculada — com `reasoning` ao lado, que é o
que permite ao advogado conferir em segundos em vez de reler o inteiro teor.

`reviewed_at` nulo é o estado normal e importante: **prazo sugerido pela IA não é prazo
do escritório até alguém confirmar** (regra 1). `human_correction` guarda o que o
humano mudou — é a única forma honesta de medir se o modelo está melhorando.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "086_publication_analyses"
down_revision: str | None = "085_ai_messages"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "publication_analyses",
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
            "publication_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publications.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("act_type", sa.Text(), nullable=True),
        sa.Column("requires_action", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deadline_days", sa.SmallInteger(), nullable=True),
        sa.Column("deadline_kind", sa.Text(), nullable=True),
        sa.Column("deadline_date", sa.Date(), nullable=True),
        sa.Column("deadline_confidence", sa.Numeric(3, 2), nullable=True),
        sa.Column(
            "suggested_task_type_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("task_types.id"),
            nullable=True,
        ),
        sa.Column(
            "suggested_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        # Regra 7: como a IA chegou ao prazo.
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column(
            "reviewed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        # Regra 11: o que o humano corrigiu — base para medir a qualidade do modelo.
        sa.Column("human_correction", postgresql.JSONB(), nullable=True),
        # Regra 13: a reanálise substitui a anterior sem apagar o histórico de correções.
        sa.Column(
            "previous_corrections",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    for statement in enable_rls_statements("publication_analyses"):
        op.execute(statement)
    op.execute(
        "CREATE INDEX ix_pub_analyses_review ON publication_analyses "
        "(tenant_id, created_at DESC) WHERE reviewed_at IS NULL"
    )

    # Regra 10: leitura automática é opção do escritório, desligada por padrão — análise
    # custa tokens e ninguém deve descobrir isso na fatura.
    op.add_column(
        "accounts",
        sa.Column(
            "ai_auto_read_publications",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("accounts", "ai_auto_read_publications")
    op.drop_table("publication_analyses")
