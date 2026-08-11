"""observabilidade da sincronização (spec 049)

Revision ID: 049_sync_observability
Revises: 048_publication_reads
Create Date: 2026-08-11

`monitored_terms.alert_id` referencia `integration_alerts` em vez de `posts` — o §4
original desenhava `alert_post_id`, mas `posts.lawsuit_id` é NOT NULL desde a spec 032
(toda tarefa pertence a um processo) e um alerta de sincronização não tem processo.
Decisão tomada com o usuário (Descobertas da 049): reaproveitar `integration_alerts`
(spec 046), que ganha `responsible_user_id`/`resolved_by`.

`integration_health` é telemetria global do sistema — mesmo padrão de
`cnj_movement_codes` (spec 046): sem `tenant_id`, sem RLS.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "049_sync_observability"
down_revision: str | None = "048_publication_reads"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "monitored_terms",
        sa.Column("consecutive_failures", sa.SmallInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "monitored_terms",
        sa.Column(
            "alert_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("integration_alerts.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "integration_alerts",
        sa.Column(
            "responsible_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "integration_alerts",
        sa.Column(
            "resolved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
    )

    op.create_table(
        "integration_health",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("integration", sa.Text(), nullable=False),
        sa.Column(
            "checked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("is_healthy", sa.Boolean(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_health_recent",
        "integration_health",
        ["integration", sa.text("checked_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_health_recent", table_name="integration_health")
    op.drop_table("integration_health")
    op.drop_column("integration_alerts", "resolved_by")
    op.drop_column("integration_alerts", "responsible_user_id")
    op.drop_column("monitored_terms", "alert_id")
    op.drop_column("monitored_terms", "consecutive_failures")
