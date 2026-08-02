"""lawsuit parties

Revision ID: 023_lawsuit_parties
Revises: 022_lawsuits
Create Date: 2026-08-02

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "023_lawsuit_parties"
down_revision: str | None = "022_lawsuits"
branch_labels: str | None = None
depends_on: str | None = None

# A ordem dos valores do enum É a ordem de exibição (regra 7): Postgres ordena enums
# pela posição de declaração, então `ORDER BY pole` já sai ATIVO → PASSIVO → CONTRARIA
# → TERCEIRO sem CASE.
party_pole = postgresql.ENUM("ATIVO", "PASSIVO", "CONTRARIA", "TERCEIRO", name="party_pole")


def upgrade() -> None:
    # Sem `party_pole.create()` explícito: `create_table` já emite o CREATE TYPE — uma
    # chamada manual antes resultaria em DuplicateObjectError.
    op.create_table(
        "lawsuit_parties",
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
            "lawsuit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lawsuits.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id"),
            nullable=False,
        ),
        sa.Column("pole", party_pole, nullable=False),
        sa.Column("is_client", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("lawsuit_id", "customer_id", "pole", name="uq_parties_lawsuit_pole"),
    )
    op.create_index("ix_parties_lawsuit", "lawsuit_parties", ["lawsuit_id"])
    op.create_index("ix_parties_customer", "lawsuit_parties", ["tenant_id", "customer_id"])
    for statement in enable_rls_statements("lawsuit_parties"):
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("lawsuit_parties")
    party_pole.drop(op.get_bind(), checkfirst=True)
