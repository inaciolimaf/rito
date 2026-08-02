"""task types (catálogo Taskscore)

Revision ID: 031_task_types
Revises: 029_folder_index
Create Date: 2026-08-02

Spec 031: catálogo de tipos de tarefa + seed dos 149 nomes documentados (149 + 3
sistêmicas = 152 linhas — o levantamento titula "152" mas lista 149) com as 19
pontuações observadas; as demais nascem com reward 0 (regra 8).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements
from app.domain.task_types.catalog import (
    DEFAULT_TASK_NAMES,
    OBSERVED_REWARDS,
    SYSTEM_TASK_NAMES,
)

revision: str = "031_task_types"
down_revision: str | None = "029_folder_index"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # create_table emite o CREATE TYPE dos enums sozinho (lição da 023: chamada manual
    # duplica) — por isso create_type=False na coluna do modelo, não aqui.
    task_complexity = postgresql.ENUM(
        "SIMPLES", "MEDIA", "MEDIA_ALTA", "ALTA", "ALTISSIMA", name="task_complexity"
    )
    task_duration = postgresql.ENUM(
        "MIN_8", "MIN_15", "MIN_30", "HOUR_1", "HOUR_2_PLUS", name="task_duration"
    )

    op.create_table(
        "task_types",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("step_id", sa.SmallInteger(), sa.ForeignKey("steps.id"), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("complexity", task_complexity, nullable=True),
        sa.Column("duration", task_duration, nullable=True),
        sa.Column("reward", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "show_in_schedule", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        # Regra 8: reward ≥ 0 — zero é válido (tarefa que não pontua).
        sa.CheckConstraint("reward >= 0", name="ck_task_types_reward"),
    )
    op.create_index("ix_task_types_step", "task_types", ["tenant_id", "step_id"])
    # Regra 7: nome único por tenant, sem acento na comparação (immutable_unaccent da 014).
    op.execute(
        "CREATE UNIQUE INDEX uq_task_types_tenant_name ON task_types "
        "(tenant_id, immutable_unaccent(lower(name)))"
    )
    for statement in enable_rls_statements("task_types"):
        op.execute(statement)

    # Seed idempotente — só atinge tenants que já existem (mesma limitação de 015/016,
    # sem spec de provisionamento de tenant ainda). Nomes do levantamento não contêm
    # aspas simples; as 19 pontuações observadas entram no seed, as demais nascem 0.
    default_values = ", ".join(
        f"('{name}', {OBSERVED_REWARDS.get(name, 0)})" for name in DEFAULT_TASK_NAMES
    )
    op.execute(f"""
        INSERT INTO task_types (tenant_id, name, reward, is_system)
        SELECT t.id, v.name, v.reward, false
        FROM tenants t
        CROSS JOIN (VALUES {default_values}) AS v(name, reward)
        ON CONFLICT (tenant_id, immutable_unaccent(lower(name))) DO NOTHING
        """)
    system_values = ", ".join(f"('{name}')" for name in SYSTEM_TASK_NAMES)
    op.execute(f"""
        INSERT INTO task_types (tenant_id, name, reward, is_system)
        SELECT t.id, v.name, 0, true
        FROM tenants t
        CROSS JOIN (VALUES {system_values}) AS v(name)
        ON CONFLICT (tenant_id, immutable_unaccent(lower(name))) DO NOTHING
        """)


def downgrade() -> None:
    op.drop_table("task_types")
    sa.Enum(name="task_complexity").drop(op.get_bind())
    sa.Enum(name="task_duration").drop(op.get_bind())
