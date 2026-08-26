"""orçamento e cache da camada de IA

Revision ID: 090_ai_budget
Revises: 089_ai_analytics
Create Date: 2026-08-26

Spec 090, alvo 2: `ai_budgets` (teto mensal por escritório, com alerta antes do
bloqueio) e `ai_cache` (resposta reaproveitada para entrada idêntica numa janela curta).

O teto existe porque IA sem limite é conta surpresa no fim do mês — e quem descobre o
problema pela fatura descobre tarde. O alerta em 80% é o que transforma "acabou o
orçamento" em "está acabando".

O cache é chaveado por (feature, modelo, mensagens): reanalisar a MESMA intimação com o
MESMO modelo é o caso real que ele evita, e ele expira rápido de propósito — resposta
velha de IA não é economia, é resposta errada.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "090_ai_budget"
down_revision: str | None = "089_ai_analytics"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "ai_budgets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        # Nulo = sem teto (o padrão de quem nunca configurou; o alerta ainda funciona).
        sa.Column("monthly_limit_usd", sa.Numeric(10, 2), nullable=True),
        sa.Column("alert_pct", sa.SmallInteger(), nullable=False, server_default=sa.text("80")),
        sa.Column("is_blocking", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", name="uq_ai_budget_tenant"),
        sa.CheckConstraint("alert_pct BETWEEN 1 AND 100", name="ck_ai_budget_alert_pct"),
    )
    for statement in enable_rls_statements("ai_budgets"):
        op.execute(statement)

    op.create_table(
        "ai_cache",
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
        # sha256 de (feature, modelo, mensagens) — o conteúdo do prompt NÃO é guardado
        # aqui (regra 13 da 081: nada de conteúdo sem opt-in).
        sa.Column("cache_key", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("response", postgresql.JSONB(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "cache_key", name="uq_ai_cache_key"),
    )
    for statement in enable_rls_statements("ai_cache"):
        op.execute(statement)
    op.execute("CREATE INDEX ix_ai_cache_expiry ON ai_cache (expires_at)")


def downgrade() -> None:
    op.drop_table("ai_cache")
    op.drop_table("ai_budgets")
