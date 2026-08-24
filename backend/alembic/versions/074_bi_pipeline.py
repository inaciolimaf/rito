"""view materializada do funil de BI (estoque e prospecção)

Revision ID: 074_bi_pipeline
Revises: 073_access_logs
Create Date: 2026-08-24

Spec 074 §4: agrega lawsuits por (tenant, mês de criação, grupo de ação) para o funil
comercial — oportunidades, fechados e arquivados da COORTE, valor da causa e honorários
dos fechados. Duas divergências do SQL literal da spec, ambas documentadas no §9 dela:

- `lawsuits` NÃO tem coluna `action_group_id` (spec 022, regra 2: grupo é derivado do
  tipo de ação e nunca reside no processo) — a view faz JOIN em `lawsuit_types` para
  chegar ao grupo;
- a chave da view é o mês de CRIAÇÃO (coorte), então ela responde "das oportunidades
  que entraram no mês, quantas fecharam" (base da taxa de conversão, regra 7) — a série
  de "fechamentos do mês" por `closure_date` (regra 5) não é derivável desta view e fica
  em tempo real no repository.

Mesmo molde das matviews anteriores (039/059/071/073): RLS não existe em matview, então
o isolamento de tenant na LEITURA vem da view barreira `bi_pipeline_monthly_visible`
(`WHERE tenant_id = current_setting('app.tenant_id', true)::uuid`, GRANT SELECT só para
rito_app); o REFRESH roda como superusuário no worker (app/workers/bi_pipeline.py) a
cada 8 horas (regra 8: até 8 h de defasagem, sinalizada na UI).

O índice parcial ix_lawsuits_idle_120 cobre o indicador "parados +120 dias" (regra 4):
ativos (não arquivados) ordenados por last_movement_at, inclusive os nulos.
"""

from alembic import op

revision: str = "074_bi_pipeline"
down_revision: str | None = "073_access_logs"
branch_labels: str | None = None
depends_on: str | None = None

_MATVIEW_SQL = """
SELECT l.tenant_id,
       date_trunc('month', l.created_at)::date AS month,
       lt.action_group_id,
       COUNT(*) AS opportunities,
       COUNT(*) FILTER (WHERE l.closure_date IS NOT NULL) AS closed,
       COUNT(*) FILTER (WHERE l.archived_date IS NOT NULL) AS archived,
       SUM(l.case_value) AS total_case_value,
       SUM(l.fees_value) FILTER (WHERE l.closure_date IS NOT NULL) AS closed_fees
FROM lawsuits l
JOIN lawsuit_types lt ON lt.id = l.lawsuit_type_id
WHERE NOT l.is_archived
GROUP BY 1, 2, 3
"""


def upgrade() -> None:
    op.execute(f"CREATE MATERIALIZED VIEW bi_pipeline_monthly AS {_MATVIEW_SQL}")
    # Índice único exigido pelo REFRESH ... CONCURRENTLY.
    op.execute(
        "CREATE UNIQUE INDEX ux_bi_pipeline "
        "ON bi_pipeline_monthly (tenant_id, month, action_group_id)"
    )
    op.execute(
        "CREATE VIEW bi_pipeline_monthly_visible AS "
        "SELECT tenant_id, month, action_group_id, opportunities, closed, archived, "
        "total_case_value, closed_fees "
        "FROM bi_pipeline_monthly "
        "WHERE tenant_id = current_setting('app.tenant_id', true)::uuid"
    )
    op.execute("GRANT SELECT ON bi_pipeline_monthly_visible TO rito_app")
    op.execute(
        "CREATE INDEX ix_lawsuits_idle_120 ON lawsuits (tenant_id, last_movement_at) "
        "WHERE NOT is_archived"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_lawsuits_idle_120")
    op.execute("DROP VIEW bi_pipeline_monthly_visible")
    op.execute("DROP MATERIALIZED VIEW bi_pipeline_monthly")
