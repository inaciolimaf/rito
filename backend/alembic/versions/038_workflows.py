"""workflows, workflow_steps e feriados nacionais

Revision ID: 038_workflows
Revises: 037_ical
Create Date: 2026-08-09

Spec 038 §4: sequência padronizada de tarefas (workflows + workflow_steps, ambas
com RLS) disparada ao mover o processo de etapa — stages.suggested_workflow_id
existia desde a 015 aguardando esta FK (ON DELETE SET NULL: excluir o workflow não
derruba a etapa, regra 9). `holidays` é tabela GLOBAL de referência (como courts,
steps, occupations): sem tenant_id, sem RLS — feriado nacional não é dado de tenant.
Seed 2026–2030: 9 fixos + móveis (Carnaval seg/ter, Sexta-feira Santa, Corpus
Christi) derivados da Páscoa de cada ano; Consciência Negra (20/11) entra porque é
feriado nacional desde 2024 (Lei 14.759/2023).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "038_workflows"
down_revision: str | None = "037_ical"
branch_labels: str | None = None
depends_on: str | None = None

_FIXED_HOLIDAYS = [
    ("01-01", "Confraternização Universal"),
    ("04-21", "Tiradentes"),
    ("05-01", "Dia do Trabalho"),
    ("09-07", "Independência do Brasil"),
    ("10-12", "Nossa Senhora Aparecida"),
    ("11-02", "Finados"),
    ("11-15", "Proclamação da República"),
    ("11-20", "Dia Nacional de Zumbi e da Consciência Negra"),
    ("12-25", "Natal"),
]

# (ano, carnaval_seg, carnaval_ter, sexta_santa, corpus_christi) — da Páscoa do ano.
_MOVABLE_HOLIDAYS = {
    2026: ("02-16", "02-17", "04-03", "06-04"),
    2027: ("02-08", "02-09", "03-26", "05-27"),
    2028: ("02-28", "02-29", "04-14", "06-15"),
    2029: ("02-12", "02-13", "03-30", "05-31"),
    2030: ("03-04", "03-05", "04-19", "06-20"),
}


def _seed_holidays() -> None:
    rows: list[str] = []
    for year in _MOVABLE_HOLIDAYS:
        for month_day, name in _FIXED_HOLIDAYS:
            rows.append(f"('{year}-{month_day}', '{name}', true)")
        carnival_mon, carnival_tue, good_friday, corpus = _MOVABLE_HOLIDAYS[year]
        rows.append(f"('{year}-{carnival_mon}', 'Carnaval', true)")
        rows.append(f"('{year}-{carnival_tue}', 'Carnaval', true)")
        rows.append(f"('{year}-{good_friday}', 'Sexta-feira Santa', true)")
        rows.append(f"('{year}-{corpus}', 'Corpus Christi', true)")
    op.execute(f"INSERT INTO holidays (date, name, is_national) VALUES {', '.join(rows)}")


def upgrade() -> None:
    op.create_table(
        "workflows",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_workflows_tenant_name"),
    )
    for statement in enable_rls_statements("workflows"):
        op.execute(statement)

    op.create_table(
        "workflow_steps",
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
            "workflow_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column(
            "task_type_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("task_types.id"),
            nullable=False,
        ),
        # Regra 2: NULL = responsável do processo no momento da aplicação.
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("days_offset", sa.SmallInteger()),
        sa.UniqueConstraint("workflow_id", "position", name="uq_workflow_steps_position"),
    )
    for statement in enable_rls_statements("workflow_steps"):
        op.execute(statement)

    op.create_table(
        "holidays",
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_national", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    _seed_holidays()

    op.create_foreign_key(
        "fk_stages_workflow",
        "stages",
        "workflows",
        ["suggested_workflow_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_stages_workflow", "stages", type_="foreignkey")
    op.drop_table("holidays")
    op.drop_table("workflow_steps")
    op.drop_table("workflows")
