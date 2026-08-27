"""automação — webhooks outbound

Revision ID: 093_webhooks
Revises: 092_automations
Create Date: 2026-08-27

Spec 093: a ação de automação que fala com o mundo de fora.

`webhook_endpoints` guarda o destino e o segredo do HMAC; `webhook_deliveries` guarda
CADA tentativa, com o corpo da resposta. A entrega é linha, não log de aplicação, por um
motivo prático: quando o n8n do escritório para de receber, a pergunta é "o que vocês
mandaram e o que voltou?" — e ela precisa de resposta seis dias depois, não só enquanto o
log estiver quente.

`failure_streak` no endpoint é o contador da regra 10: vinte falhas seguidas desativam o
destino. É contador, e não `COUNT(*)` sobre as entregas, porque o que importa é a
SEQUÊNCIA — uma entrega bem-sucedida zera tudo.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "093_webhooks"
down_revision: str | None = "092_automations"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "webhook_endpoints",
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
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("secret", sa.Text(), nullable=False),
        sa.Column(
            "headers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("failure_streak", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_webhook_endpoints_name"),
    )
    for statement in enable_rls_statements("webhook_endpoints"):
        op.execute(statement)

    op.create_table(
        "webhook_deliveries",
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
            "endpoint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("automation_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_kind", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("attempt", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column("status_code", sa.SmallInteger(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        # Quando a próxima tentativa pode acontecer (regra 3: 1, 5 e 15 minutos).
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    for statement in enable_rls_statements("webhook_deliveries"):
        op.execute(statement)
    op.execute(
        "CREATE INDEX ix_deliveries_endpoint ON webhook_deliveries (endpoint_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_deliveries_failed ON webhook_deliveries (tenant_id, created_at DESC) "
        "WHERE delivered_at IS NULL"
    )
    # A varredura do worker pergunta só isto: que entrega ainda deve ser retentada?
    op.execute(
        "CREATE INDEX ix_deliveries_due ON webhook_deliveries (next_attempt_at) "
        "WHERE delivered_at IS NULL AND next_attempt_at IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_table("webhook_deliveries")
    op.drop_table("webhook_endpoints")
