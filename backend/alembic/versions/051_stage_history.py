"""lawsuit_stage_history + stage_entered_at (spec 051 — CRM: board Kanban)

Revision ID: 051_stage_history
Revises: 050_sync_runs_unified
Create Date: 2026-08-11

`stage_entered_at` é mantida por trigger (regra 6): qualquer UPDATE em
`lawsuits.stage_id` — pelo Kanban ou não — rearma o relógio sozinha, sem
depender de todo call site lembrar de setar. `lawsuit_stage_history` (regra 5)
é gravada pela aplicação (`LawsuitService`), não pelo trigger, porque
`changed_by` exige saber QUEM mudou — informação que só existe no request,
não numa trigger pura de banco.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls

revision: str = "051_stage_history"
down_revision: str | None = "050_sync_runs_unified"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "lawsuits",
        sa.Column(
            "stage_entered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "lawsuit_stage_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "lawsuit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lawsuits.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_stage_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stages.id"),
            nullable=True,
        ),
        sa.Column(
            "to_stage_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stages.id"),
            nullable=False,
        ),
        sa.Column(
            "changed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_stage_history", "lawsuit_stage_history", ["lawsuit_id", sa.text("changed_at DESC")]
    )
    enable_rls("lawsuit_stage_history")

    op.execute("""
        CREATE OR REPLACE FUNCTION set_lawsuit_stage_entered_at() RETURNS trigger AS $$
        BEGIN
          IF NEW.stage_id IS DISTINCT FROM OLD.stage_id THEN
            NEW.stage_entered_at := now();
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """)
    op.execute("""
        CREATE TRIGGER trg_lawsuits_stage_entered_at
        BEFORE UPDATE ON lawsuits
        FOR EACH ROW EXECUTE FUNCTION set_lawsuit_stage_entered_at()
        """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_lawsuits_stage_entered_at ON lawsuits")
    op.execute("DROP FUNCTION IF EXISTS set_lawsuit_stage_entered_at")
    op.drop_table("lawsuit_stage_history")
    op.drop_column("lawsuits", "stage_entered_at")
