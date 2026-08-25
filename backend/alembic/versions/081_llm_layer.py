"""camada LLM (OpenRouter)

Revision ID: 081_llm_layer
Revises: 079_partnerships
Create Date: 2026-08-26

Spec 081 §4: `ai_feature_config` (modelo POR FEATURE, escolhido pelo usuário — regra 2:
nenhum modelo hardcoded) e `ai_usage` (tokens, custo e latência de todo uso, inclusive
o que falhou — regra 6). As duas com RLS: consumo de IA é dado do escritório.

`store_prompts` e as colunas `prompt`/`response_text` de `ai_usage` não estavam no DDL
da spec e implementam a regra 13: por padrão **nada de conteúdo é persistido**, só
metadados; o tenant que quiser guardar prompt e resposta liga o opt-in por feature, e
só então as colunas são preenchidas.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "081_llm_layer"
down_revision: str | None = "079_partnerships"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "ai_feature_config",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("feature_key", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("fallback_model", sa.Text(), nullable=True),
        sa.Column("temperature", sa.Numeric(3, 2), nullable=False, server_default=sa.text("0.20")),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        # Regra 13: opt-in explícito para persistir conteúdo (LGPD).
        sa.Column("store_prompts", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "feature_key", name="uq_ai_feature_config"),
        sa.CheckConstraint("temperature >= 0 AND temperature <= 2", name="ck_ai_temperature"),
    )
    for statement in enable_rls_statements("ai_feature_config"):
        op.execute(statement)

    op.create_table(
        "ai_usage",
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
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("feature_key", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        # 'ok' | 'error' | 'fallback' (regra 5/6).
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        # Regra 13: nulos sem opt-in — é o estado normal.
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    for statement in enable_rls_statements("ai_usage"):
        op.execute(statement)
    # `ix_ai_usage_tenant` (só tenant_id) já vem de enable_rls_statements — este é o
    # índice do relatório de consumo, por período.
    op.execute("CREATE INDEX ix_ai_usage_tenant_created ON ai_usage (tenant_id, created_at DESC)")
    op.execute(
        "CREATE INDEX ix_ai_usage_feature ON ai_usage (tenant_id, feature_key, created_at DESC)"
    )


def downgrade() -> None:
    op.drop_table("ai_usage")
    op.drop_table("ai_feature_config")
