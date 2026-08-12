"""dunning_rules e dunning_attempts (spec 061 — Financeiro: inadimplência)

Revision ID: 061_dunning
Revises: 059_daily_balances
Create Date: 2026-08-12

`UNIQUE (transaction_id, rule_id)` em `dunning_attempts` é a regra 4 (uma tentativa por
regra por lançamento) codificada no banco — e também o que faz o envio MANUAL (regra 8)
funcionar sem caso especial: `rule_id` fica `NULL` nesses envios, e Postgres trata NULL
como distinto em UNIQUE, então vários envios manuais do mesmo lançamento nunca colidem
com a constraint. `rule_id` é `ON DELETE SET NULL` — a régua nunca é excluída pela API
(só `GET`/`PUT`, sem `DELETE` no contrato da spec), mas se algum dia for, o histórico de
tentativas sobrevive.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "061_dunning"
down_revision: str | None = "059_daily_balances"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("CREATE TYPE dunning_channel AS ENUM ('EMAIL', 'SMS', 'WHATSAPP')")
    op.execute("CREATE TYPE dunning_status AS ENUM ('SENT', 'FAILED', 'SKIPPED')")

    op.create_table(
        "dunning_rules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("days_offset", sa.SmallInteger(), nullable=False),
        sa.Column(
            "channel",
            postgresql.ENUM("EMAIL", "SMS", "WHATSAPP", name="dunning_channel", create_type=False),
            nullable=False,
        ),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "tenant_id", "days_offset", "channel", name="uq_dunning_rules_offset_channel"
        ),
    )
    for statement in enable_rls_statements("dunning_rules"):
        op.execute(statement)

    op.create_table(
        "dunning_attempts",
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
            "transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "rule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dunning_rules.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "channel",
            postgresql.ENUM("EMAIL", "SMS", "WHATSAPP", name="dunning_channel", create_type=False),
            nullable=False,
        ),
        sa.Column("sent_to", sa.Text(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM("SENT", "FAILED", "SKIPPED", name="dunning_status", create_type=False),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "sent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("transaction_id", "rule_id", name="uq_dunning_attempts_tx_rule"),
    )
    op.create_index(
        "ix_dunning_tx", "dunning_attempts", ["transaction_id", sa.text("sent_at DESC")]
    )
    for statement in enable_rls_statements("dunning_attempts"):
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("dunning_attempts")
    op.drop_table("dunning_rules")
    op.execute("DROP TYPE dunning_status")
    op.execute("DROP TYPE dunning_channel")
