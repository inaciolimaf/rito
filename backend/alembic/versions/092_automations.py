"""automação — gatilhos e ações

Revision ID: 092_automations
Revises: 091_document_extractions
Create Date: 2026-08-27

Spec 092: generaliza o workflow da 038. Lá era uma regra só, embutida ("mudou de etapa,
cria as tarefas do fluxo"); aqui é gatilho → ação → tempo, com o escritório escrevendo as
regras.

Três tabelas para o desenho e uma para o histórico:

- `automations` — o gatilho e o que o restringe;
- `automation_actions` — a sequência, com o controle de tempo de cada passo;
- `automation_runs` — uma execução, com onde ela parou e por quê;
- `automation_run_steps` — passo a passo do que aconteceu, inclusive o que foi PULADO.

O passo a passo não é luxo de auditoria: é o que responde "por que a tarefa não foi
criada?", que é a pergunta que chega ao suporte. Sem ele, condição falsa e ação nunca
alcançada ficam indistinguíveis.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "092_automations"
down_revision: str | None = "091_document_extractions"
branch_labels: str | None = None
depends_on: str | None = None


def _tenant_column() -> sa.Column[postgresql.UUID]:
    return sa.Column(
        "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
    )


def _id_column() -> sa.Column[postgresql.UUID]:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )


def upgrade() -> None:
    op.create_table(
        "automations",
        _id_column(),
        _tenant_column(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("trigger_kind", sa.Text(), nullable=False),
        sa.Column(
            "trigger_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_automations_name"),
    )
    for statement in enable_rls_statements("automations"):
        op.execute(statement)
    op.execute(
        "CREATE INDEX ix_automations_trigger ON automations (tenant_id, trigger_kind) "
        "WHERE is_active"
    )

    op.create_table(
        "automation_actions",
        _id_column(),
        _tenant_column(),
        sa.Column(
            "automation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("automations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("action_kind", sa.Text(), nullable=False),
        sa.Column(
            "action_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("delay_kind", sa.Text(), nullable=False, server_default=sa.text("'immediate'")),
        sa.Column("delay_value", sa.SmallInteger(), nullable=True),
        sa.Column("condition", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.UniqueConstraint("automation_id", "position", name="uq_automation_actions_position"),
        sa.CheckConstraint(
            "delay_kind IN ('immediate', 'business_days', 'calendar_days', 'after_previous')",
            name="ck_automation_actions_delay_kind",
        ),
    )
    for statement in enable_rls_statements("automation_actions"):
        op.execute(statement)

    op.create_table(
        "automation_runs",
        _id_column(),
        _tenant_column(),
        sa.Column(
            "automation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("automations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "trigger_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("subject_type", sa.Text(), nullable=True),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'running'")),
        sa.Column(
            "actions_completed", sa.SmallInteger(), nullable=False, server_default=sa.text("0")
        ),
        # Regra 7: a profundidade viaja com o evento — é o que impede duas automações de
        # se alimentarem em pingue-pongue até o banco encher.
        sa.Column("chain_depth", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        # Onde a execução parou, quando parou: `next_action_at` para atraso em dias,
        # `waiting_on_id` para `after_previous` (a tarefa que precisa ser concluída).
        sa.Column("next_position", sa.SmallInteger(), nullable=True),
        sa.Column("next_action_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("waiting_on_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'waiting', 'done', 'failed')",
            name="ck_automation_runs_status",
        ),
    )
    for statement in enable_rls_statements("automation_runs"):
        op.execute(statement)
    op.execute(
        "CREATE INDEX ix_runs_automation ON automation_runs (automation_id, started_at DESC)"
    )
    # A varredura do worker pergunta só isto: que execução está esperando e já venceu?
    op.execute(
        "CREATE INDEX ix_runs_due ON automation_runs (next_action_at) "
        "WHERE status = 'waiting' AND next_action_at IS NOT NULL"
    )

    op.create_table(
        "automation_run_steps",
        _id_column(),
        _tenant_column(),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("automation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("action_kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Regra 8: idempotência é uma restrição do banco, não uma intenção do código.
        sa.UniqueConstraint("run_id", "position", name="uq_automation_run_steps_position"),
        sa.CheckConstraint(
            "status IN ('done', 'skipped', 'failed')", name="ck_automation_run_steps_status"
        ),
    )
    for statement in enable_rls_statements("automation_run_steps"):
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("automation_run_steps")
    op.drop_table("automation_runs")
    op.drop_table("automation_actions")
    op.drop_table("automations")
