"""account_daily_balances (spec 059 — Financeiro: dashboard e fluxo de caixa)

Revision ID: 059_daily_balances
Revises: 058_internal_transactions
Create Date: 2026-08-12

View materializada do saldo diário por conta, cumulativa (regra 6 — "saldo da conta
numa data vem da view materializada"). Mesmo padrão de `user_monthly_scores`
(migration 039): a view em si é global (sem RLS possível em matview), o isolamento
de tenant é da view barreira `account_daily_balances_visible`, e o refresh roda como
superusuário (worker `app/workers/financial_dashboard.py`).

`balance_delta` é só a soma cumulativa dos lançamentos PAGOS (por `payment_date`,
nunca `due_date` — projeção é regime `cash_flow`, calculado ao vivo, não aqui) e NÃO
inclui `bank_accounts.initial_amount`: o saldo final é `initial_amount + balance_delta`,
calculado no repositório. Isso evita invalidar a view toda vez que alguém edita o
saldo inicial de uma conta. Lançamento interno (regra 1 da spec 058) nunca entra —
mesmo filtro `NOT is_internal` de `ix_tx_effective`/`lawsuit_financial_totals`.
"""

from alembic import op

revision: str = "059_daily_balances"
down_revision: str | None = "058_internal_transactions"
branch_labels: str | None = None
depends_on: str | None = None

_MATVIEW_SQL = """
WITH movements AS (
    SELECT tenant_id, debit_account_id AS account_id, payment_date AS day,
           CASE kind WHEN 'RECEITA' THEN amount ELSE -amount END AS delta
    FROM transactions
    WHERE payment_date IS NOT NULL AND NOT is_internal AND debit_account_id IS NOT NULL
    UNION ALL
    SELECT tenant_id, credit_account_id AS account_id, payment_date AS day, amount AS delta
    FROM transactions
    WHERE payment_date IS NOT NULL AND NOT is_internal
      AND kind = 'TRANSFERENCIA' AND credit_account_id IS NOT NULL
),
daily AS (
    SELECT tenant_id, account_id, day, SUM(delta) AS day_delta
    FROM movements
    GROUP BY tenant_id, account_id, day
)
SELECT tenant_id, account_id, day,
       SUM(day_delta) OVER (
           PARTITION BY tenant_id, account_id ORDER BY day
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS balance_delta
FROM daily
"""


def upgrade() -> None:
    op.execute(f"CREATE MATERIALIZED VIEW account_daily_balances AS {_MATVIEW_SQL}")
    # Índice único exigido pelo REFRESH ... CONCURRENTLY.
    op.execute("CREATE UNIQUE INDEX ux_adb ON account_daily_balances (tenant_id, account_id, day)")
    op.execute(
        "CREATE VIEW account_daily_balances_visible AS "
        "SELECT tenant_id, account_id, day, balance_delta "
        "FROM account_daily_balances "
        "WHERE tenant_id = current_setting('app.tenant_id', true)::uuid"
    )
    op.execute("GRANT SELECT ON account_daily_balances_visible TO rito_app")


def downgrade() -> None:
    op.execute("DROP VIEW account_daily_balances_visible")
    op.execute("DROP MATERIALIZED VIEW account_daily_balances")
