"""lawsuit financials and lifecycle

Revision ID: 024_lawsuit_financials
Revises: 023_lawsuit_parties
Create Date: 2026-08-02

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "024_lawsuit_financials"
down_revision: str | None = "023_lawsuit_parties"
branch_labels: str | None = None
depends_on: str | None = None

contingency_level = postgresql.ENUM("PROVAVEL", "POSSIVEL", "REMOTA", name="contingency_level")
lawsuit_outcome = postgresql.ENUM("GANHO", "PERDIDO", "ACORDO", name="lawsuit_outcome")


def upgrade() -> None:
    # Diferente do create_table (migration 023), `add_column` NÃO emite o CREATE TYPE do
    # enum sozinho — aqui o `.create()` explícito é obrigatório.
    contingency_level.create(op.get_bind())
    lawsuit_outcome.create(op.get_bind())
    op.add_column("lawsuits", sa.Column("case_value", sa.Numeric(14, 2), nullable=True))
    op.add_column("lawsuits", sa.Column("fees_value", sa.Numeric(14, 2), nullable=True))
    op.add_column("lawsuits", sa.Column("fees_percentage", sa.Numeric(5, 2), nullable=True))
    op.add_column("lawsuits", sa.Column("contingency", contingency_level, nullable=True))
    op.add_column("lawsuits", sa.Column("closure_date", sa.Date(), nullable=True))
    op.add_column("lawsuits", sa.Column("transit_date", sa.Date(), nullable=True))
    op.add_column("lawsuits", sa.Column("archived_date", sa.Date(), nullable=True))
    op.add_column("lawsuits", sa.Column("outcome", lawsuit_outcome, nullable=True))
    op.create_check_constraint(
        "ck_fees_pct",
        "lawsuits",
        "fees_percentage IS NULL OR fees_percentage BETWEEN 0 AND 100",
    )
    # Regra 3: fechamento ≤ trânsito ≤ arquivamento.
    op.create_check_constraint(
        "ck_cycle",
        "lawsuits",
        "(transit_date IS NULL OR closure_date IS NULL OR transit_date >= closure_date) "
        "AND (archived_date IS NULL OR transit_date IS NULL OR archived_date >= transit_date)",
    )
    op.execute(
        "CREATE INDEX ix_lawsuits_closure ON lawsuits (tenant_id, closure_date) "
        "WHERE closure_date IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_lawsuits_transit ON lawsuits (tenant_id, transit_date) "
        "WHERE transit_date IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_lawsuits_archived ON lawsuits (tenant_id, archived_date) "
        "WHERE archived_date IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_lawsuits_outcome ON lawsuits (tenant_id, outcome) "
        "WHERE outcome IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_lawsuits_outcome")
    op.execute("DROP INDEX IF EXISTS ix_lawsuits_archived")
    op.execute("DROP INDEX IF EXISTS ix_lawsuits_transit")
    op.execute("DROP INDEX IF EXISTS ix_lawsuits_closure")
    op.drop_constraint("ck_cycle", "lawsuits", type_="check")
    op.drop_constraint("ck_fees_pct", "lawsuits", type_="check")
    for column in (
        "outcome",
        "archived_date",
        "transit_date",
        "closure_date",
        "contingency",
        "fees_percentage",
        "fees_value",
        "case_value",
    ):
        op.drop_column("lawsuits", column)
    lawsuit_outcome.drop(op.get_bind(), checkfirst=True)
    contingency_level.drop(op.get_bind(), checkfirst=True)
