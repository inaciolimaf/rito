"""view materializada de alocação de custos do BI

Revision ID: 077_bi_costs
Revises: 076_bi_cycles
Create Date: 2026-08-24

Spec 077 §4: agrega por (tenant, competência) o custo fixo (grupos DRE 2, 3, 5 e 7 —
folha, encargos, fixas e bancárias; ids confirmados no seed da migration 054), o custo
de marketing (grupo 8) e os pontos do Taskscore concluídos no mês, derivando o custo
por ponto (regra 2: fixo ÷ pontos). Uma divergência do SQL literal da spec, já
documentada em outras specs:

- a spec escreve `JOIN financial_categories c` sem qualificar as colunas de
  `transactions`; aqui as colunas vêm qualificadas (`t.`, `c.`, `pu.`) — mesma
  cardinalidade e semântica.

Regra 8 (mês sem pontos → nulo, nunca infinito) vem do CASE: `p.points > 0` falso (ou
mês sem pontos, LEFT JOIN → NULL) rende `cost_per_point` NULL — nunca divisão por
zero. `is_internal` e TRANSFERENCIA ficam fora do custo (regra: interno e
transferência fora): o WHERE exige kind='DESPESA' (transferência tem kind próprio,
spec 056) e NOT is_internal (spec 058).

Mesmo molde das matviews anteriores (039/059/071/073/074/075/076): RLS não existe em
matview, então o isolamento de tenant na LEITURA vem da view barreira
`bi_cost_allocation_visible` (`WHERE tenant_id = current_setting('app.tenant_id',
true)::uuid`, GRANT SELECT só para rito_app); o REFRESH roda como superusuário no
worker (app/workers/bi_costs.py) a cada 8 horas, mesmo intervalo da 074/075/076.
"""

from alembic import op

revision: str = "077_bi_costs"
down_revision: str | None = "076_bi_cycles"
branch_labels: str | None = None
depends_on: str | None = None

_MATVIEW_SQL = """
WITH monthly_fixed AS (
  SELECT t.tenant_id, t.competence,
         SUM(t.amount) FILTER (WHERE c.dre_group_id IN (2, 3, 5, 7)) AS fixed_cost,
         SUM(t.amount) FILTER (WHERE c.dre_group_id = 8)             AS marketing_cost
  FROM transactions t
  JOIN financial_categories c ON c.id = t.category_id
  WHERE t.kind = 'DESPESA' AND NOT t.is_internal
  GROUP BY 1, 2
),
monthly_points AS (
  SELECT pu.tenant_id, date_trunc('month', pu.completed_at)::date AS competence,
         SUM(pu.points_earned) AS points
  FROM post_users pu
  WHERE pu.completed_at IS NOT NULL
  GROUP BY 1, 2
)
SELECT f.tenant_id, f.competence, f.fixed_cost, f.marketing_cost,
       p.points,
       CASE WHEN p.points > 0 THEN f.fixed_cost / p.points END AS cost_per_point
FROM monthly_fixed f
LEFT JOIN monthly_points p
       ON p.tenant_id = f.tenant_id AND p.competence = f.competence
"""


def upgrade() -> None:
    op.execute(f"CREATE MATERIALIZED VIEW bi_cost_allocation AS {_MATVIEW_SQL}")
    # Índice único exigido pelo REFRESH ... CONCURRENTLY.
    op.execute("CREATE UNIQUE INDEX ux_bi_cost ON bi_cost_allocation (tenant_id, competence)")
    op.execute(
        "CREATE VIEW bi_cost_allocation_visible AS "
        "SELECT tenant_id, competence, fixed_cost, marketing_cost, points, cost_per_point "
        "FROM bi_cost_allocation "
        "WHERE tenant_id = current_setting('app.tenant_id', true)::uuid"
    )
    op.execute("GRANT SELECT ON bi_cost_allocation_visible TO rito_app")


def downgrade() -> None:
    op.execute("DROP VIEW bi_cost_allocation_visible")
    op.execute("DROP MATERIALIZED VIEW bi_cost_allocation")
