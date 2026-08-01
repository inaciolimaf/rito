"""accounts

Revision ID: 011_accounts
Revises: 006_refatoracao_fundacao_indices
Create Date: 2026-08-01

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "011_accounts"
down_revision: str | None = "006_refatoracao_fundacao_indices"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "accounts",
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
            unique=True,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("alternate_name", sa.Text(), nullable=False),
        sa.Column("identification", sa.Text(), nullable=False),
        sa.Column("country", sa.Text(), nullable=False, server_default="BRASIL"),
        sa.Column("state", sa.CHAR(2), nullable=False),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("postal_code", sa.Text(), nullable=False),
        sa.Column("street", sa.Text(), nullable=False),
        sa.Column("region", sa.Text(), nullable=False),
        sa.Column("cellphone", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("email_admin", postgresql.CITEXT(), nullable=False),
        sa.Column("site", sa.Text(), nullable=True),
        sa.Column("timezone", sa.Text(), nullable=False, server_default="America/Sao_Paulo"),
        sa.Column("logo_key", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    # `tenant_id` já é UNIQUE (1:1 com tenants) — a constraint acima cria o índice sozinha.
    # Pula o último statement de enable_rls_statements() (CREATE INDEX ix_accounts_tenant),
    # que duplicaria esse índice sem necessidade (spec 010, checklist "Banco": sem índice
    # redundante).
    for statement in enable_rls_statements("accounts")[:-1]:
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("accounts")
