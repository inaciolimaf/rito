"""is_stagnant + stagnant_since (spec 052 — CRM: estagnação e métricas)

Revision ID: 052_stagnation
Revises: 051_stage_history
Create Date: 2026-08-11

Colunas puramente derivadas (regra 1/5): `is_stagnant`/`stagnant_since` não têm
trigger — quem escreve é `StagnationService` (mover processo, job diário, troca de
`stagnant_days` da etapa). Nenhuma migração de dado histórico: todo processo nasce
`is_stagnant=false` e o primeiro recálculo (job das 3h ou o gatilho manual) preenche
de verdade.
"""

import sqlalchemy as sa

from alembic import op

revision: str = "052_stagnation"
down_revision: str | None = "051_stage_history"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "lawsuits",
        sa.Column("is_stagnant", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("lawsuits", sa.Column("stagnant_since", sa.Date(), nullable=True))
    op.create_index(
        "ix_lawsuits_stagnant",
        "lawsuits",
        ["tenant_id", "is_stagnant"],
        postgresql_where=sa.text("is_stagnant AND NOT is_archived"),
    )


def downgrade() -> None:
    op.drop_index("ix_lawsuits_stagnant", table_name="lawsuits")
    op.drop_column("lawsuits", "stagnant_since")
    op.drop_column("lawsuits", "is_stagnant")
