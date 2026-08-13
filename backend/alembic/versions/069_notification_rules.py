"""notification_rules + user_notification_preferences (spec 069 — Notificações)

Revision ID: 069_notification_rules
Revises: 068_public_templates
Create Date: 2026-08-13

`UNIQUE (tenant_id, event)` em `notification_rules` é o que faz "sem regra" e
"responsible_user_id NULL" serem estados distintos (regra 1/2 da spec): a ausência de
linha é "não configurado", a linha com `responsible_user_id` nulo é "não notificar"
configurado explicitamente.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "069_notification_rules"
down_revision: str | None = "068_public_templates"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE notification_event AS ENUM " "('NOVO_CLIENTE', 'NOVO_PROCESSO', 'INTIMACAO')"
    )
    op.execute("CREATE TYPE notification_channel AS ENUM ('EMAIL', 'SMS', 'WHATSAPP')")

    op.create_table(
        "notification_rules",
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
            "event",
            postgresql.ENUM(
                "NOVO_CLIENTE",
                "NOVO_PROCESSO",
                "INTIMACAO",
                name="notification_event",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "responsible_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "channels",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "event", name="uq_notification_rules_event"),
    )
    for statement in enable_rls_statements("notification_rules"):
        op.execute(statement)

    op.create_table(
        "user_notification_preferences",
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
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "channel",
            postgresql.ENUM(
                "EMAIL", "SMS", "WHATSAPP", name="notification_channel", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint(
            "tenant_id", "user_id", "channel", name="uq_user_notification_preferences"
        ),
    )
    for statement in enable_rls_statements("user_notification_preferences"):
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("user_notification_preferences")
    op.drop_table("notification_rules")
    op.execute("DROP TYPE notification_channel")
    op.execute("DROP TYPE notification_event")
