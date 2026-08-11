"""transactions (spec 056 — Financeiro: lançamentos)

Revision ID: 056_transactions
Revises: 055_bank_accounts
Create Date: 2026-08-11

4 constraints codificam as regras críticas no banco (spec §4): transferência exige
origem+destino diferentes e nada mais exige; não-transferência exige categoria+centro
de custo; processo exige cliente; baixa nunca no futuro. A regra 1 (tipo do lançamento
casa com o tipo da categoria) fica de fora de propósito — cruza `transactions.kind`
com `financial_categories.type` de OUTRA tabela, o que um CHECK simples não alcança;
validada na aplicação (`TransactionService`).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "056_transactions"
down_revision: str | None = "055_bank_accounts"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("CREATE TYPE transaction_kind AS ENUM ('RECEITA', 'DESPESA', 'TRANSFERENCIA')")

    op.create_table(
        "transactions",
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
            "kind",
            postgresql.ENUM(
                "RECEITA", "DESPESA", "TRANSFERENCIA", name="transaction_kind", create_type=False
            ),
            nullable=False,
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "debit_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bank_accounts.id"),
            nullable=True,
        ),
        sa.Column(
            "credit_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bank_accounts.id"),
            nullable=True,
        ),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("financial_categories.id"),
            nullable=True,
        ),
        sa.Column(
            "cost_center_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cost_centers.id"),
            nullable=True,
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id"),
            nullable=True,
        ),
        sa.Column(
            "lawsuit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lawsuits.id"), nullable=True
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=True),
        sa.Column("competence", sa.Date(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.CheckConstraint("amount > 0", name="ck_tx_amount_positive"),
        sa.CheckConstraint(
            "kind <> 'TRANSFERENCIA' OR (credit_account_id IS NOT NULL "
            "AND debit_account_id IS NOT NULL AND debit_account_id <> credit_account_id)",
            name="ck_tx_transfer_accounts",
        ),
        sa.CheckConstraint(
            "kind = 'TRANSFERENCIA' OR (category_id IS NOT NULL AND cost_center_id IS NOT NULL)",
            name="ck_tx_non_transfer_needs_category",
        ),
        sa.CheckConstraint(
            "lawsuit_id IS NULL OR customer_id IS NOT NULL", name="ck_tx_lawsuit_needs_customer"
        ),
        sa.CheckConstraint(
            "payment_date IS NULL OR payment_date <= CURRENT_DATE", name="ck_tx_payment_not_future"
        ),
    )
    op.create_index("ix_tx_due", "transactions", ["tenant_id", sa.text("due_date DESC")])
    op.create_index(
        "ix_tx_payment",
        "transactions",
        ["tenant_id", sa.text("payment_date DESC")],
        postgresql_where=sa.text("payment_date IS NOT NULL"),
    )
    op.create_index("ix_tx_competence", "transactions", ["tenant_id", sa.text("competence DESC")])
    op.create_index(
        "ix_tx_lawsuit",
        "transactions",
        ["lawsuit_id"],
        postgresql_where=sa.text("lawsuit_id IS NOT NULL"),
    )
    op.create_index(
        "ix_tx_customer",
        "transactions",
        ["tenant_id", "customer_id"],
        postgresql_where=sa.text("customer_id IS NOT NULL"),
    )
    op.create_index(
        "ix_tx_open",
        "transactions",
        ["tenant_id", "due_date"],
        postgresql_where=sa.text("payment_date IS NULL"),
    )
    for statement in enable_rls_statements("transactions"):
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("transactions")
    op.execute("DROP TYPE transaction_kind")
