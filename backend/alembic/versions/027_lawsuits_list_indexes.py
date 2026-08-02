"""lawsuits list indexes + last_movement_at

Revision ID: 027_lawsuits_list_indexes
Revises: 026_lawsuit_movements
Create Date: 2026-08-02

"""

import sqlalchemy as sa

from alembic import op

revision: str = "027_lawsuits_list_indexes"
down_revision: str | None = "026_lawsuit_movements"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # `last_movement_at` materializado (spec 027 §4): "parado há +90 dias" com subquery a
    # cada listagem não escala — a trigger mantém o máximo de occurred_at a cada insert.
    op.add_column("lawsuits", sa.Column("last_movement_at", sa.DateTime(timezone=True)))
    op.execute(
        "CREATE INDEX ix_lawsuits_last_movement ON lawsuits "
        "(tenant_id, last_movement_at DESC NULLS LAST)"
    )
    op.execute("CREATE INDEX ix_lawsuits_created ON lawsuits (tenant_id, created_at DESC)")
    op.execute("""
        CREATE OR REPLACE FUNCTION set_lawsuit_last_movement() RETURNS trigger AS $$
        BEGIN
          UPDATE lawsuits
          SET last_movement_at = GREATEST(
            COALESCE(last_movement_at, NEW.occurred_at), NEW.occurred_at
          )
          WHERE id = NEW.lawsuit_id;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """)
    op.execute("""
        CREATE TRIGGER trg_movements_last_movement
        AFTER INSERT ON lawsuit_movements
        FOR EACH ROW EXECUTE FUNCTION set_lawsuit_last_movement()
        """)
    # Backfill para movimentações que já existiam antes da coluna.
    op.execute("""
        UPDATE lawsuits
        SET last_movement_at = sub.max_occurred
        FROM (
          SELECT lawsuit_id, MAX(occurred_at) AS max_occurred
          FROM lawsuit_movements GROUP BY lawsuit_id
        ) AS sub
        WHERE lawsuits.id = sub.lawsuit_id
        """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_movements_last_movement ON lawsuit_movements")
    op.execute("DROP FUNCTION IF EXISTS set_lawsuit_last_movement")
    op.execute("DROP INDEX IF EXISTS ix_lawsuits_created")
    op.execute("DROP INDEX IF EXISTS ix_lawsuits_last_movement")
    op.drop_column("lawsuits", "last_movement_at")
