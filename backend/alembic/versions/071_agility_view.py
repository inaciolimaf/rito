"""view materializada de agilidade diária por usuário

Revision ID: 071_agility_view
Revises: 069_notification_rules
Create Date: 2026-08-15

Spec 071 §4: agrega post_users/posts por (tenant, usuário, dia de conclusão) para os
painéis de Agilidade e Produtividade. Guarda SOMAS (não médias) porque o relatório
soma sobre um intervalo arbitrário de dias — média de médias diárias distorceria o
resultado quando os dias têm volumes diferentes de tarefas concluídas.

Mesmo molde da matview de Taskscore (migration 039): RLS não existe em matview, então
o isolamento de tenant na LEITURA vem da view barreira `agility_daily_visible`
(`WHERE tenant_id = current_setting('app.tenant_id', true)::uuid`, GRANT SELECT só
para rito_app); o REFRESH roda como superusuário no worker de manutenção
(app/workers/agility.py), nunca pela conexão da aplicação.
"""

from alembic import op

revision: str = "071_agility_view"
down_revision: str | None = "069_notification_rules"
branch_labels: str | None = None
depends_on: str | None = None

_MATVIEW_SQL = """
SELECT pu.tenant_id,
       pu.user_id,
       date_trunc('day', pu.completed_at)::date AS day,
       COUNT(*) FILTER (
         WHERE p.deadline_date IS NULL OR pu.completed_at::date <= p.deadline_date
       ) AS on_time,
       COUNT(*) FILTER (
         WHERE p.deadline_date IS NOT NULL AND pu.completed_at::date > p.deadline_date
       ) AS late,
       COUNT(*) AS completed_count,
       COALESCE(
         SUM(EXTRACT(EPOCH FROM (pu.completed_at - p.created_at)) / 86400.0), 0
       ) AS sum_days_to_complete,
       COALESCE(
         SUM(GREATEST(pu.completed_at::date - p.deadline_date, 0)) FILTER (
           WHERE p.deadline_date IS NOT NULL AND pu.completed_at::date > p.deadline_date
         ), 0
       ) AS sum_delay_days
FROM post_users pu
JOIN posts p ON p.id = pu.post_id
WHERE pu.completed_at IS NOT NULL
GROUP BY 1, 2, 3
"""


def upgrade() -> None:
    op.execute(f"CREATE MATERIALIZED VIEW agility_daily AS {_MATVIEW_SQL}")
    # Índice único exigido pelo REFRESH ... CONCURRENTLY.
    op.execute("CREATE UNIQUE INDEX ux_agility_daily ON agility_daily (tenant_id, user_id, day)")
    op.execute(
        "CREATE VIEW agility_daily_visible AS "
        "SELECT tenant_id, user_id, day, on_time, late, completed_count, "
        "sum_days_to_complete, sum_delay_days "
        "FROM agility_daily "
        "WHERE tenant_id = current_setting('app.tenant_id', true)::uuid"
    )
    op.execute("GRANT SELECT ON agility_daily_visible TO rito_app")


def downgrade() -> None:
    op.execute("DROP VIEW agility_daily_visible")
    op.execute("DROP MATERIALIZED VIEW agility_daily")
