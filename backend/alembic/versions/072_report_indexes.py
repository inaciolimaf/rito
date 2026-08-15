"""índices para os relatórios tabulares

Revision ID: 072_report_indexes
Revises: 071_agility_view
Create Date: 2026-08-15

Spec 072 §4: os relatórios de ganhos/perdidos filtram por `outcome`+`closure_date`; o
de partes contrárias filtra `lawsuit_parties` por `pole = 'CONTRARIA'`. Nenhuma tabela
nova — os 9 relatórios são tempo real sobre tabelas já existentes (regra 2).
"""

from alembic import op

revision: str = "072_report_indexes"
down_revision: str | None = "071_agility_view"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_lawsuits_outcome_date ON lawsuits (tenant_id, outcome, closure_date) "
        "WHERE outcome IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_parties_contrary ON lawsuit_parties (tenant_id, customer_id) "
        "WHERE pole = 'CONTRARIA'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_parties_contrary")
    op.execute("DROP INDEX ix_lawsuits_outcome_date")
