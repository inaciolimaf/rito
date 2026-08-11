"""sync_runs unificado — DJEN e DataJud (spec 050, refatoração, alvo 1)

Revision ID: 050_sync_runs_unified
Revises: 049_sync_observability
Create Date: 2026-08-11

`term_sync_runs` (spec 043) só cobria o DJEN — o DataJud (047) não tinha
histórico de execução nenhum. Em vez de criar uma segunda tabela, a spec 050
generaliza esta: renomeada para `sync_runs`, `term_id` vira opcional,
`lawsuit_id` (novo, opcional) cobre o DataJud, `integration` distingue as
duas. CHECK garante exatamente um dos dois assuntos por linha — nunca os
dois, nunca nenhum. Aditivo: nenhuma linha existente muda (`term_id`
continua preenchido, `integration` vira 'djen' por DEFAULT).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "050_sync_runs_unified"
down_revision: str | None = "049_sync_observability"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.rename_table("term_sync_runs", "sync_runs")
    op.alter_column("sync_runs", "term_id", nullable=True)
    op.add_column(
        "sync_runs",
        sa.Column(
            "lawsuit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lawsuits.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.add_column(
        "sync_runs",
        sa.Column("integration", sa.Text(), nullable=False, server_default="djen"),
    )
    op.create_check_constraint(
        "ck_sync_runs_subject", "sync_runs", "num_nonnulls(term_id, lawsuit_id) = 1"
    )
    op.create_index("ix_sync_runs_lawsuit", "sync_runs", ["lawsuit_id", sa.text("started_at DESC")])


def downgrade() -> None:
    op.drop_index("ix_sync_runs_lawsuit", table_name="sync_runs")
    op.drop_constraint("ck_sync_runs_subject", "sync_runs", type_="check")
    op.drop_column("sync_runs", "integration")
    op.drop_column("sync_runs", "lawsuit_id")
    op.alter_column("sync_runs", "term_id", nullable=False)
    op.rename_table("sync_runs", "term_sync_runs")
