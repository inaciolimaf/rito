"""tenants and rls

Revision ID: 003_tenants_and_rls
Revises: 002_initial_extensions
Create Date: 2026-08-01

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "003_tenants_and_rls"
down_revision: str | None = "002_initial_extensions"
branch_labels: str | None = None
depends_on: str | None = None

_CREATE_APP_ROLE = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'rito_app') THEN
        CREATE ROLE rito_app LOGIN PASSWORD 'rito_app'
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
    END IF;
END
$$;
"""

_GRANT_CONNECT = """
DO $$
BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO rito_app', current_database());
END
$$;
"""

_GRANT_APP_ROLE_STATEMENTS = [
    _GRANT_CONNECT,
    "GRANT USAGE ON SCHEMA public TO rito_app",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rito_app",
    (
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO rito_app"
    ),
]

# Não derruba a role `rito_app` no downgrade: ela é compartilhada entre bancos
# do mesmo cluster (`rito` e `rito_test`) — cada banco só desfaz seus próprios
# grants; a role em si só seria removida manualmente, fora de uma migration.
_REVOKE_APP_ROLE_STATEMENTS = [
    (
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM rito_app"
    ),
    "REVOKE SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public FROM rito_app",
    "REVOKE USAGE ON SCHEMA public FROM rito_app",
]


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    op.execute(_CREATE_APP_ROLE)
    for statement in _GRANT_APP_ROLE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in _REVOKE_APP_ROLE_STATEMENTS:
        op.execute(statement)
    op.drop_table("tenants")
