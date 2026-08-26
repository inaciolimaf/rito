"""agentes de petição por área

Revision ID: 087_legal_agents
Revises: 086_publication_analyses
Create Date: 2026-08-26

Spec 087 §4: `legal_agents` (19 agentes de sistema + os que o escritório personalizar) e
`agent_generations` (cada minuta produzida, com o modelo, os tokens e quem pediu).

`legal_agents.tenant_id` é NULO nos agentes de sistema — os 19 são catálogo global, como
`courts` e `steps`. Isso exige política de RLS própria (`tenant_id IS NULL OR
tenant_id = current`), a mesma forma já usada por `integration_alerts` e
`external_requests`, e por isso a exceção está registrada em `docs/SEGURANCA-RLS.md` e
no teste de auditoria da spec 080 — que falharia se ela aparecesse sem justificativa.

`original_system_prompt` guarda o prompt de fábrica (regra 10): o escritório pode
reescrever o dele e voltar atrás sem depender de migration nem de backup.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.domain.legal_agents.catalog import AGENT_SEEDS

revision: str = "087_legal_agents"
down_revision: str | None = "086_publication_analyses"
branch_labels: str | None = None
depends_on: str | None = None

_CURRENT = "current_setting('app.tenant_id', true)::uuid"


def upgrade() -> None:
    op.create_table(
        "legal_agents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        # NULO = agente de sistema, visível a todos os escritórios.
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=True
        ),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("practice_area", sa.Text(), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        # Regra 10: o de fábrica, para restaurar.
        sa.Column("original_system_prompt", sa.Text(), nullable=False),
        sa.Column(
            "default_template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "code", name="uq_legal_agents_code"),
    )
    op.execute("ALTER TABLE legal_agents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE legal_agents FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON legal_agents "
        f"USING (tenant_id IS NULL OR tenant_id = {_CURRENT}) "
        f"WITH CHECK (tenant_id = {_CURRENT})"
    )
    op.execute("CREATE INDEX ix_legal_agents_tenant ON legal_agents (tenant_id)")

    op.create_table(
        "agent_generations",
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
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("legal_agents.id"),
            nullable=False,
        ),
        sa.Column(
            "lawsuit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lawsuits.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "thread_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_threads.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("user_instructions", sa.Text(), nullable=True),
        # `{"format": "html", "html": "..."}` — ver Descobertas da spec sobre o formato.
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column(
            "template_used_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        # Regra 6: citações que o agente tentou inventar e foram removidas.
        sa.Column(
            "warnings", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "generated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "saved_template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    from app.core.rls import enable_rls_statements

    for statement in enable_rls_statements("agent_generations"):
        op.execute(statement)
    op.execute(
        "CREATE INDEX ix_agent_gen_lawsuit ON agent_generations (lawsuit_id, created_at DESC)"
    )

    # Seed dos 19 agentes de sistema (spec 087 §4).
    agents = sa.table(
        "legal_agents",
        sa.column("code", sa.Text),
        sa.column("name", sa.Text),
        sa.column("practice_area", sa.Text),
        sa.column("system_prompt", sa.Text),
        sa.column("original_system_prompt", sa.Text),
    )
    op.bulk_insert(
        agents,
        [
            {
                "code": seed.code,
                "name": seed.name,
                "practice_area": seed.practice_area,
                "system_prompt": seed.system_prompt(),
                "original_system_prompt": seed.system_prompt(),
            }
            for seed in AGENT_SEEDS
        ],
    )


def downgrade() -> None:
    op.drop_table("agent_generations")
    op.drop_table("legal_agents")
