"""registro de acessos e livro de ponto

Revision ID: 073_access_logs
Revises: 072_report_indexes
Create Date: 2026-08-15

Spec 073 §4: `access_logs` (tabela de domínio, RLS) grava um evento por login bem-
sucedido (regra 1/3, desligado por padrão via `accounts.track_access_logs`);
`timesheet_daily` agrega por dia no timezone da CONTA (regra 12 — por isso o JOIN com
`accounts` dentro da própria definição da matview, não em tempo de leitura) e guarda o
IP do último acesso do dia (usado pelo relatório `access_logs` da spec 072, que só
tem colunas de dia agregado — não uma linha por evento bruto).

Mesmo molde de 039/071: RLS não existe em matview, então a view barreira
`timesheet_daily_visible` embute o filtro de tenant; REFRESH roda como superusuário
no worker de manutenção (app/workers/timesheet.py).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "073_access_logs"
down_revision: str | None = "072_report_indexes"
branch_labels: str | None = None
depends_on: str | None = None

_MATVIEW_SQL = """
SELECT al.tenant_id,
       al.user_id,
       (al.occurred_at AT TIME ZONE 'UTC' AT TIME ZONE a.timezone)::date AS day,
       MIN(al.occurred_at) AS first_access,
       MAX(al.occurred_at) AS last_access,
       COUNT(*) AS access_count,
       (array_agg(al.ip_address ORDER BY al.occurred_at DESC))[1] AS last_ip
FROM access_logs al
JOIN accounts a ON a.tenant_id = al.tenant_id
GROUP BY 1, 2, 3
"""


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column(
            "track_access_logs", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )

    op.create_table(
        "access_logs",
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
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    for statement in enable_rls_statements("access_logs"):
        op.execute(statement)
    op.execute(
        "CREATE INDEX ix_access_user_day ON access_logs (tenant_id, user_id, occurred_at DESC)"
    )

    op.execute(f"CREATE MATERIALIZED VIEW timesheet_daily AS {_MATVIEW_SQL}")
    op.execute("CREATE UNIQUE INDEX ux_timesheet ON timesheet_daily (tenant_id, user_id, day)")
    op.execute(
        "CREATE VIEW timesheet_daily_visible AS "
        "SELECT tenant_id, user_id, day, first_access, last_access, access_count, last_ip "
        "FROM timesheet_daily "
        "WHERE tenant_id = current_setting('app.tenant_id', true)::uuid"
    )
    op.execute("GRANT SELECT ON timesheet_daily_visible TO rito_app")


def downgrade() -> None:
    op.execute("DROP VIEW timesheet_daily_visible")
    op.execute("DROP MATERIALIZED VIEW timesheet_daily")
    op.drop_table("access_logs")
    op.drop_column("accounts", "track_access_logs")
