"""ical feed token em users

Revision ID: 037_ical
Revises: 036_inbox_preferences
Create Date: 2026-08-09

Spec 037 §4: feed iCal por usuário. `ical_token` (32 bytes aleatórios, gerado sob
demanda no enable) + `ical_enabled`. A rota pública /ical/{token}.ics não conhece o
tenant antes da query e a role de aplicação é NOBYPASSRLS — a função
`lookup_ical_feed` (SECURITY DEFINER, dona = superusuário da migration) resolve
(tenant_id, user_id) por match exato do token sem abrir exceção no RLS: é o único
caminho cross-tenant e expõe só o par de ids, nunca linhas.
"""

import sqlalchemy as sa

from alembic import op

revision: str = "037_ical"
down_revision: str | None = "036_inbox_preferences"
branch_labels: str | None = None
depends_on: str | None = None

_LOOKUP_FUNCTION = """
CREATE OR REPLACE FUNCTION lookup_ical_feed(p_token text)
RETURNS TABLE(tenant_id uuid, user_id uuid)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT tenant_id, id FROM users
    WHERE ical_enabled AND ical_token = p_token
$$;
"""

_DROP_FUNCTION = "DROP FUNCTION IF EXISTS lookup_ical_feed(text);"


def upgrade() -> None:
    op.add_column("users", sa.Column("ical_token", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column("ical_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_unique_constraint("uq_users_ical_token", "users", ["ical_token"])
    op.execute(_LOOKUP_FUNCTION)


def downgrade() -> None:
    op.execute(_DROP_FUNCTION)
    op.drop_constraint("uq_users_ical_token", "users", type_="unique")
    op.drop_column("users", "ical_enabled")
    op.drop_column("users", "ical_token")
