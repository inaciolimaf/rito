"""view materializada de ciclos e honorários do BI

Revision ID: 076_bi_cycles
Revises: 075_bi_vintage
Create Date: 2026-08-24

Spec 076 §4: uma linha por processo FECHADO (`closure_date IS NOT NULL`) com os 4 ciclos
em dias (regra 1), honorários e a receita paga vinculada (regra 6: kind='RECEITA', não
interna, com `payment_date`). Duas divergências do SQL literal da spec, as mesmas já
documentadas no §9 das specs 074/075:

- `lawsuits` NÃO tem coluna `action_group_id` (spec 022, regra 2: grupo é derivado do
  tipo de ação e nunca reside no processo) — a view faz JOIN em `lawsuit_types` para
  chegar ao grupo; cardinalidade e semântica preservadas;
- a tabela `transactions` existe com exatamente as colunas citadas (spec 056:
  kind/is_internal/payment_date/lawsuit_id/amount) — nenhum ajuste de nome necessário.

Regra 2 (nulo ≠ zero) vem de graça da aritmética de datas do Postgres: qualquer ciclo
com data faltando resulta NULL, nunca zero — zero só quando as duas datas coincidem
("no mesmo dia"). A definição canônica dos ciclos em Python (usada nos testes de
unidade) é `app.domain.bi.service.compute_cycle_days`, espelho deste SQL.

Mesmo molde das matviews anteriores (039/059/071/073/074/075): RLS não existe em
matview, então o isolamento de tenant na LEITURA vem da view barreira
`bi_lawsuit_cycles_visible` (`WHERE tenant_id = current_setting('app.tenant_id',
true)::uuid`, GRANT SELECT só para rito_app); o REFRESH roda como superusuário no
worker (app/workers/bi_cycles.py) a cada 8 horas, mesmo intervalo da 074/075.
"""

from alembic import op

revision: str = "076_bi_cycles"
down_revision: str | None = "075_bi_vintage"
branch_labels: str | None = None
depends_on: str | None = None

_MATVIEW_SQL = """
SELECT l.tenant_id,
       l.id AS lawsuit_id,
       lt.action_group_id,
       l.lawsuit_type_id,
       l.outcome,
       l.created_at::date AS created_date,
       l.closure_date,
       l.transit_date,
       l.archived_date,
       l.fees_value,
       -- prospecção: criação → fechamento do contrato (regra 1)
       (l.closure_date - l.created_at::date) AS prospecting_days,
       -- produção: fechamento → trânsito em julgado
       (l.transit_date - l.closure_date) AS production_days,
       -- execução: trânsito → arquivamento
       (l.archived_date - l.transit_date) AS execution_days,
       -- rotação completa: criação → arquivamento
       (l.archived_date - l.created_at::date) AS full_cycle_days,
       -- regra 6: receita PAGA, não interna, vinculada ao processo
       COALESCE((SELECT SUM(t.amount) FROM transactions t
                 WHERE t.lawsuit_id = l.id AND t.kind = 'RECEITA'
                   AND NOT t.is_internal AND t.payment_date IS NOT NULL), 0) AS revenue
FROM lawsuits l
JOIN lawsuit_types lt ON lt.id = l.lawsuit_type_id
WHERE l.closure_date IS NOT NULL
"""


def upgrade() -> None:
    op.execute(f"CREATE MATERIALIZED VIEW bi_lawsuit_cycles AS {_MATVIEW_SQL}")
    # Índice único exigido pelo REFRESH ... CONCURRENTLY.
    op.execute("CREATE UNIQUE INDEX ux_bi_cycles ON bi_lawsuit_cycles (tenant_id, lawsuit_id)")
    op.execute(
        "CREATE VIEW bi_lawsuit_cycles_visible AS "
        "SELECT tenant_id, lawsuit_id, action_group_id, lawsuit_type_id, outcome, "
        "created_date, closure_date, transit_date, archived_date, fees_value, "
        "prospecting_days, production_days, execution_days, full_cycle_days, revenue "
        "FROM bi_lawsuit_cycles "
        "WHERE tenant_id = current_setting('app.tenant_id', true)::uuid"
    )
    op.execute("GRANT SELECT ON bi_lawsuit_cycles_visible TO rito_app")


def downgrade() -> None:
    op.execute("DROP VIEW bi_lawsuit_cycles_visible")
    op.execute("DROP MATERIALIZED VIEW bi_lawsuit_cycles")
