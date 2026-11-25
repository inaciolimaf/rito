"""136: a competência dos pontos passa a ser a do escritório (matview bi_cost_allocation)

Revision ID: 136_competencia_do_escritorio
Revises: 133_papel_de_leitura_da_ia
Create Date: 2026-09-08

A matview `bi_cost_allocation` (migration 077) divide custo fixo por pontos concluídos, e
os dois lados da divisão mediam **meses diferentes**:

- `monthly_fixed` agrupa por `t.competence`, coluna `DATE` derivada do vencimento — mês de
  escritório, sem hora nenhuma;
- `monthly_points` agrupava por `date_trunc('month', pu.completed_at)`, e `completed_at` é
  `timestamptz` — mês de **UTC**.

Medido no Postgres: uma tarefa concluída às 22h30 de 31/01/2026 em São Paulo recebia
competência `2026-02-01` na view e `2026-01-01` no escritório. Os pontos saíam de janeiro;
o custo fixo de janeiro ficava onde estava. `cost_per_point` de janeiro sobe (menos pontos,
mesmo custo), o de fevereiro desce — e como `allocated_cost` de **cada processo** é
`pontos × cost_per_point do mês`, o erro não fica num card: ele se espalha pela coluna de
custo de todos os processos da tela.

É o membro mais caro da família da dívida 32, e o único em que o fuso não move uma linha de
lugar numa lista: ele desalinha os dois lados de uma divisão. O resultado continua
plausível, com duas casas decimais, e não há como conferir olhando.

## Por que uma migration nova, e não uma edição da 077

`CLAUDE.md` §9: migration commitada não se edita. E `CREATE OR REPLACE` não existe para
view materializada — a troca é `DROP` + `CREATE`, o que arrasta a view barreira
`bi_cost_allocation_visible`, o índice único do `REFRESH CONCURRENTLY` e os dois `GRANT`
(o de `rito_app`, da 077, e o de `rito_ai`, da 133). Todos são recriados aqui, na mesma
ordem, e o `CREATE MATERIALIZED VIEW` já nasce populado (o `WITH DATA` é o padrão), então
não há janela em que a tela do BI apareça vazia esperando o worker das 8 h.

## De onde vem o fuso dentro do SQL

De `accounts.timezone` (spec 011), com `LEFT JOIN` por `tenant_id` — que é `UNIQUE` na
tabela desde a 011, então a junção não multiplica linha de ponto nenhuma. O `COALESCE` com
`America/Sao_Paulo` cobre o escritório sem linha de conta e repete o padrão do `Clock`
(spec 114): na falta do fuso configurado, o padrão do produto — nunca o do servidor.

O REFRESH roda como superusuário no worker (`app/workers/bi_costs.py`), fora de qualquer
contexto de tenant, e é por isso que o fuso precisa vir da junção e não de
`current_setting('app.tenant_id')`: a matview é de todos os escritórios ao mesmo tempo.

`app/domain/bi/repository.py::_allocated_costs_cte` calcula a MESMA competência do lado do
Python (`_office_month`, com o fuso do `Clock`) para casar o join do rateio. As duas
expressões precisam continuar concordando — é o que
`tests/integration/test_bi_costs.py::test_competencia_dos_pontos_e_a_do_escritorio`
verifica ponta a ponta.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "136_competencia_do_escritorio"
down_revision: str | None = "133_papel_de_leitura_da_ia"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# O fuso do escritório dono da linha. `COALESCE` porque a conta pode não ter linha ainda.
_FUSO = "COALESCE(a.timezone, 'America/Sao_Paulo')"

# Idêntica à 077 exceto por `monthly_points`, que agora corta o mês no fuso do escritório.
_MATVIEW_SQL = f"""
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
  SELECT pu.tenant_id,
         date_trunc('month', timezone({_FUSO}, pu.completed_at))::date AS competence,
         SUM(pu.points_earned) AS points
  FROM post_users pu
  LEFT JOIN accounts a ON a.tenant_id = pu.tenant_id
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

# O SQL da 077, palavra por palavra — é para onde o `downgrade` volta.
_MATVIEW_SQL_077 = """
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


def _recriar(sql: str) -> None:
    """Troca a definição da matview e reconstrói tudo que pendurava nela.

    A ordem importa: a view barreira depende da matview, então ela cai primeiro e volta
    por último — com os dois `GRANT` que existiam antes (`rito_app` da 077, `rito_ai` da
    133). Esquecer o segundo deixaria o text-to-SQL da spec 089 sem a relação que o
    `sql_guard` promete que ele pode ler, e o
    `test_ai_sql_role.py` acusaria na hora.
    """
    op.execute("DROP VIEW IF EXISTS bi_cost_allocation_visible")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS bi_cost_allocation")
    op.execute(f"CREATE MATERIALIZED VIEW bi_cost_allocation AS {sql}")
    op.execute("CREATE UNIQUE INDEX ux_bi_cost ON bi_cost_allocation (tenant_id, competence)")
    op.execute(
        "CREATE VIEW bi_cost_allocation_visible AS "
        "SELECT tenant_id, competence, fixed_cost, marketing_cost, points, cost_per_point "
        "FROM bi_cost_allocation "
        "WHERE tenant_id = current_setting('app.tenant_id', true)::uuid"
    )
    op.execute("GRANT SELECT ON bi_cost_allocation_visible TO rito_app")
    op.execute("GRANT SELECT ON bi_cost_allocation_visible TO rito_ai")


def upgrade() -> None:
    _recriar(_MATVIEW_SQL)


def downgrade() -> None:
    _recriar(_MATVIEW_SQL_077)
