"""controle de janela da sincronização DJEN

Revision ID: 044_sync_control
Revises: 043_monitored_terms
Create Date: 2026-08-10

Spec 044, §4: `last_captured_date` marca até onde a captura do termo já chegou.
A janela incremental parte dela (com 1 dia de sobreposição, regra 3); nula, a
primeira execução usa `backfill_from` (regra 4).
"""

import sqlalchemy as sa

from alembic import op

revision: str = "044_sync_control"
down_revision: str | None = "043_monitored_terms"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("monitored_terms", sa.Column("last_captured_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("monitored_terms", "last_captured_date")
