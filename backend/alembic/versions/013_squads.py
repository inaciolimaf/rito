"""squads

Revision ID: 013_squads
Revises: 012_users_full
Create Date: 2026-08-01

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "013_squads"
down_revision: str | None = "012_users_full"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "squads",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_squads_tenant_name"),
    )
    for statement in enable_rls_statements("squads"):
        op.execute(statement)

    # `squad_members` é uma tabela de associação pura (spec 013 declara PK composta
    # `(squad_id, user_id)`) — usa `id` UUID surrogate + UNIQUE em vez de PK composta para
    # ficar consistente com `Base` (toda outra tabela do projeto tem PK `id` UUID única;
    # `Base` não foi desenhado para acomodar PK composta). Efeito é o mesmo: um par
    # squad+user não se repete.
    op.create_table(
        "squad_members",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "squad_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("squads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint("squad_id", "user_id", name="uq_squad_members_squad_user"),
    )
    op.create_index("ix_squad_members_squad_id", "squad_members", ["squad_id"])
    op.create_index("ix_squad_members_user_id", "squad_members", ["user_id"])
    for statement in enable_rls_statements("squad_members"):
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("squad_members")
    op.drop_table("squads")
