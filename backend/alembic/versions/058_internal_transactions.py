"""internal transactions (spec 058 — Financeiro: registro interno e anexos)

Revision ID: 058_internal_transactions
Revises: 057_transaction_series
Create Date: 2026-08-11

`is_internal` marca lançamento que existe só pra controle (honorário a combinar,
provisão) — nunca entra em saldo/fluxo de caixa/DRE/DFC (regra 1). O índice parcial
`ix_tx_effective` é o que mantém rápidas as consultas que hoje já filtram `NOT
is_internal` (ex.: `lawsuit_financial_totals`, spec 056) conforme esses cálculos forem
sendo implementados de verdade (a maioria ainda não existe — ver Descobertas).
"""

import sqlalchemy as sa

from alembic import op

revision: str = "058_internal_transactions"
down_revision: str | None = "057_transaction_series"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("is_internal", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("transactions", sa.Column("internal_note", sa.Text(), nullable=True))
    op.create_index(
        "ix_tx_effective",
        "transactions",
        ["tenant_id", "due_date"],
        postgresql_where=sa.text("NOT is_internal"),
    )


def downgrade() -> None:
    op.drop_index("ix_tx_effective", table_name="transactions")
    op.drop_column("transactions", "internal_note")
    op.drop_column("transactions", "is_internal")
