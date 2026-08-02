"""lawsuit movements + user preferences

Revision ID: 026_lawsuit_movements
Revises: 024_lawsuit_financials
Create Date: 2026-08-02

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "026_lawsuit_movements"
down_revision: str | None = "024_lawsuit_financials"
branch_labels: str | None = None
depends_on: str | None = None

movement_origin = postgresql.ENUM("TRIBUNAL", "MANUAL", name="movement_origin")


def upgrade() -> None:
    op.create_table(
        "lawsuit_movements",
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
        sa.Column("origin", movement_origin, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("header", sa.Text(), nullable=True),
        sa.Column("external_code", sa.Integer(), nullable=True),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        # NULLs não colidem: movimentações manuais (sem external_id) coexistem livremente.
        sa.UniqueConstraint("tenant_id", "lawsuit_id", "external_id", name="uq_movements_external"),
    )
    op.execute(
        "CREATE INDEX ix_movements_lawsuit ON lawsuit_movements (lawsuit_id, occurred_at DESC)"
    )
    op.create_index("ix_movements_origin", "lawsuit_movements", ["tenant_id", "origin"])
    for statement in enable_rls_statements("lawsuit_movements"):
        op.execute(statement)

    # Preferências por usuário (spec 026, regra 7) — chave/valor genérico; a primeira
    # consumidora é a seleção de tipos da timeline ("lawsuit_timeline_kinds").
    op.add_column(
        "users",
        sa.Column(
            "preferences",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "preferences")
    op.drop_table("lawsuit_movements")
    movement_origin.drop(op.get_bind(), checkfirst=True)
