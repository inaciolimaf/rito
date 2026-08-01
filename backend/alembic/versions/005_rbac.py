"""rbac

Revision ID: 005_rbac
Revises: 004_auth
Create Date: 2026-08-01

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "005_rbac"
down_revision: str | None = "004_auth"
branch_labels: str | None = None
depends_on: str | None = None

_user_role = postgresql.ENUM(
    "GESTOR", "ADMINISTRADOR", "COLABORADOR", name="user_role", create_type=False
)
_financial_access = postgresql.ENUM(
    "NONE", "READ_ONLY", "FULL", name="financial_access", create_type=False
)


def upgrade() -> None:
    _user_role.create(op.get_bind(), checkfirst=True)
    _financial_access.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "users",
        sa.Column("role", _user_role, nullable=False, server_default="COLABORADOR"),
    )
    op.add_column(
        "users",
        sa.Column("financial_access", _financial_access, nullable=False, server_default="NONE"),
    )


def downgrade() -> None:
    op.drop_column("users", "financial_access")
    op.drop_column("users", "role")

    _financial_access.drop(op.get_bind(), checkfirst=True)
    _user_role.drop(op.get_bind(), checkfirst=True)
