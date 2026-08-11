"""transaction_series (spec 057 — Financeiro: recorrência e parcelamento)

Revision ID: 057_transaction_series
Revises: 056_transactions
Create Date: 2026-08-11

`is_installment` distingue as 2 modalidades: parcelado (`total_installments` obrigatório,
gerado todo de uma vez na criação) e recorrente (`recurrence` obrigatório, gerado aos poucos
por um worker que mantém `generated_until` — regra 4). Os 2 CHECK espelham a regra 1/11 da
spec: um exclui o outro.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "057_transaction_series"
down_revision: str | None = "056_transactions"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE financial_recurrence AS ENUM "
        "('MENSAL', 'BIMESTRAL', 'TRIMESTRAL', 'SEMESTRAL', 'ANUAL')"
    )

    op.create_table(
        "transaction_series",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("is_installment", sa.Boolean(), nullable=False),
        sa.Column(
            "recurrence",
            postgresql.ENUM(
                "MENSAL",
                "BIMESTRAL",
                "TRIMESTRAL",
                "SEMESTRAL",
                "ANUAL",
                name="financial_recurrence",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("total_installments", sa.SmallInteger(), nullable=True),
        sa.Column("until_date", sa.Date(), nullable=True),
        sa.Column("generated_until", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "is_installment = (total_installments IS NOT NULL)",
            name="ck_series_installment_has_count",
        ),
        sa.CheckConstraint(
            "total_installments IS NULL OR total_installments BETWEEN 2 AND 100",
            name="ck_series_installment_range",
        ),
        sa.CheckConstraint(
            "is_installment OR recurrence IS NOT NULL", name="ck_series_recurrence_needs_period"
        ),
    )
    for statement in enable_rls_statements("transaction_series"):
        op.execute(statement)

    op.add_column(
        "transactions",
        sa.Column(
            "series_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transaction_series.id"),
            nullable=True,
        ),
    )
    op.add_column("transactions", sa.Column("installment_number", sa.SmallInteger(), nullable=True))
    op.create_index(
        "ix_tx_series",
        "transactions",
        ["series_id", "installment_number"],
        postgresql_where=sa.text("series_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_tx_series", table_name="transactions")
    op.drop_column("transactions", "installment_number")
    op.drop_column("transactions", "series_id")
    op.drop_table("transaction_series")
    op.execute("DROP TYPE financial_recurrence")
