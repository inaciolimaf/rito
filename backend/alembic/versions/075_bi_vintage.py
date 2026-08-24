"""view materializada de safra e qualidade do BI

Revision ID: 075_bi_vintage
Revises: 074_bi_pipeline
Create Date: 2026-08-24

Spec 075 §4: agrega lawsuits por (tenant, ANO de closure_date, grupo de ação) — a safra
é o conjunto de processos FECHADOS num ano (regra 3: safra = ano de `closure_date`, não
de criação), acompanhado até o fim do ciclo (trânsito em julgado, arquivamento).
Uma divergência do SQL literal da spec, a mesma já documentada no §9 da 074:

- `lawsuits` NÃO tem coluna `action_group_id` (spec 022, regra 2: grupo é derivado do
  tipo de ação e nunca reside no processo) — a view faz JOIN em `lawsuit_types` para
  chegar ao grupo; cardinalidade e semântica preservadas.

Ao contrário da bi_pipeline_monthly (074), aqui não há filtro `NOT is_archived`: a safra
acompanha o processo até o arquivamento (campos `archived` e `avg_cycle_days`, regras 4
e 7), então arquivados precisam permanecer na agregação.

Mesmo molde das matviews anteriores (039/059/071/073/074): RLS não existe em matview,
então o isolamento de tenant na LEITURA vem da view barreira `bi_vintage_visible`
(`WHERE tenant_id = current_setting('app.tenant_id', true)::uuid`, GRANT SELECT só para
rito_app); o REFRESH roda como superusuário no worker (app/workers/bi_vintage.py) a
cada 8 horas, mesmo intervalo da 074.

`avg_cycle_days` (regra 7): `archived_date - closure_date` entre datas rende inteiro de
dias; o FILTER garante que só arquivados entram na média — processos ainda em ciclo não
distorcem o ciclo médio.
"""

from alembic import op

revision: str = "075_bi_vintage"
down_revision: str | None = "074_bi_pipeline"
branch_labels: str | None = None
depends_on: str | None = None

_MATVIEW_SQL = """
SELECT l.tenant_id,
       EXTRACT(YEAR FROM l.closure_date)::int AS vintage_year,
       lt.action_group_id,
       COUNT(*) AS total,
       COUNT(*) FILTER (WHERE l.outcome = 'GANHO')   AS won,
       COUNT(*) FILTER (WHERE l.outcome = 'PERDIDO') AS lost,
       COUNT(*) FILTER (WHERE l.outcome = 'ACORDO')  AS settled,
       COUNT(*) FILTER (WHERE l.outcome IS NULL)     AS in_progress,
       COUNT(*) FILTER (WHERE l.transit_date IS NOT NULL)  AS transited,
       COUNT(*) FILTER (WHERE l.archived_date IS NOT NULL) AS archived,
       AVG(l.archived_date - l.closure_date)
           FILTER (WHERE l.archived_date IS NOT NULL) AS avg_cycle_days
FROM lawsuits l
JOIN lawsuit_types lt ON lt.id = l.lawsuit_type_id
WHERE l.closure_date IS NOT NULL
GROUP BY 1, 2, 3
"""


def upgrade() -> None:
    op.execute(f"CREATE MATERIALIZED VIEW bi_vintage AS {_MATVIEW_SQL}")
    # Índice único exigido pelo REFRESH ... CONCURRENTLY.
    op.execute(
        "CREATE UNIQUE INDEX ux_bi_vintage "
        "ON bi_vintage (tenant_id, vintage_year, action_group_id)"
    )
    op.execute(
        "CREATE VIEW bi_vintage_visible AS "
        "SELECT tenant_id, vintage_year, action_group_id, total, won, lost, settled, "
        "in_progress, transited, archived, avg_cycle_days "
        "FROM bi_vintage "
        "WHERE tenant_id = current_setting('app.tenant_id', true)::uuid"
    )
    op.execute("GRANT SELECT ON bi_vintage_visible TO rito_app")


def downgrade() -> None:
    op.execute("DROP VIEW bi_vintage_visible")
    op.execute("DROP MATERIALIZED VIEW bi_vintage")
