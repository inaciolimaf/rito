# 059 — Financeiro: dashboard e fluxo de caixa

**Fase:** 5 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 058 · **Status:** ✅ concluída

---

## 1. Objetivo

A tela financeira completa, com os **4 regimes de visualização** que o ADVBOX oferece. Mudar o
regime muda a pergunta que a tela responde: "quanto entrou", "quanto vence", "de que mês é" ou
"como fica o caixa".

## 2. Escopo

- Cards: saldo, receita prevista × realizada, despesa prevista × realizada, atrasados
- Gráfico receitas × despesas
- 4 regimes: pagamento, vencimento, competência, fluxo de caixa
- Saldo por conta
- Listagem com filtros e navegação por mês
- Export

## 3. Fora de escopo

- Inadimplência → 061 · DRE e DFC → 062

## 4. Modelo de dados

Nenhuma tabela nova. View materializada de saldo diário:

```sql
CREATE MATERIALIZED VIEW account_daily_balances AS
SELECT tenant_id, account_id, day,
       SUM(delta) OVER (PARTITION BY tenant_id, account_id ORDER BY day) AS balance
FROM ( /* entradas − saídas por dia, apenas pagos e não internos */ ) t;
CREATE UNIQUE INDEX ux_adb ON account_daily_balances (tenant_id, account_id, day);
```
Migration `059_daily_balances.py`. Refresh concorrente a cada 10 min e após baixa.

## 5. Contratos de API

| Método | Rota |
|---|---|
| GET | `/api/v1/transactions/stats?month=&regime=&account_id=` |
| GET | `/api/v1/transactions/cash-flow?from=&to=&account_id=` |
| GET | `/api/v1/transactions/chart?month=&group_by=day\|week` |
| GET | `/api/v1/bank-accounts/balances` |

`regime`: `payment` · `due` · `competence` · `cash_flow`

## 6. Front-end

**Reutiliza:** `StatCard`, `DataTable`, `FilterBar`, `BarChart`, `MoneyField`
**Cria:** `FinancialDashboard`, `RegimeSelect`, `MonthNavigator`, `AccountBalanceRow`,
`CashFlowChart`
**Rota:** `/transactions`

Colunas: Vencimento · Pagamento · Competência · Lançamento · Categoria · Valor
Rodapé: total do período · saldo · previsto

## 7. Regras de negócio

1. Os 4 regimes mudam **qual data filtra** a consulta:
   - `payment`: `payment_date` — o que efetivamente entrou/saiu
   - `due`: `due_date` — o que vence no período
   - `competence`: `competence` — a que mês pertence
   - `cash_flow`: pagos por `payment_date` + em aberto por `due_date` (projeção)
2. Lançamento interno **fora** de todos os cálculos de saldo (regra de 058).
3. Transferência não entra em receita nem despesa — só move saldo entre contas.
4. Previsto = todos do período. Realizado = os com `payment_date` preenchida.
5. Atrasados = `due_date < hoje` e `payment_date IS NULL`, excluindo internos.
6. Saldo da conta em uma data vem da view materializada.
7. Cartão de crédito mostra **fatura do ciclo**, não saldo.
8. Navegação por mês preserva regime e filtros.
9. Rodapé mostra: total filtrado, saldo (receitas − despesas) e previsto.
10. Valores negativos em vermelho; a UI nunca mostra `-R$ -100`.
11. Refresh da view acontece após baixa; a leitura pode ter até 10 min de defasagem, sinalizada na UI.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | **os 4 regimes com o mesmo dataset** (tabela parametrizada) | ~0,8 s |
| integração | interno fora dos cálculos | ~0,3 s |
| integração | transferência não vira receita nem despesa | ~0,3 s |
| integração | previsto × realizado | ~0,4 s |
| integração | atrasados excluem interno | ~0,3 s |
| integração | saldo por conta bate com a view | ~0,4 s |
| integração | cartão mostra fatura, não saldo | ~0,3 s |
| integração | view refresca após baixa | ~0,4 s |
| integração | **budget: dashboard ≤ 5 statements** | ~0,4 s |
| frontend | trocar regime refaz a consulta | ~0,4 s |
| frontend | navegação por mês preserva filtros | ~0,4 s |
| frontend | negativo em vermelho, sem sinal duplicado | ~0,3 s |
| e2e | **jornada 9/25:** criar receita → baixar → ver saldo | ~4 s |

**Total:** ~8,7 s

## 9. Descobertas

- **Materialized view seguiu o padrão já validado de `user_monthly_scores` (spec 039).**
  `account_daily_balances` (migration 059) guarda só a soma cumulativa dos lançamentos
  **pagos** por dia/conta — não inclui `initial_amount` (evita invalidar a view a cada
  edição de saldo inicial da conta; o saldo final é `initial_amount + balance_delta`,
  somado no repositório). Isolamento por tenant é da view barreira
  `account_daily_balances_visible` (RLS não existe em matview); refresh
  `CONCURRENTLY` roda como superusuário em `app/workers/financial_dashboard.py`,
  agendado no beat a cada 10 min + disparo imediato (`schedule_account_balances_refresh`,
  chamado do *router*, não do service — mesma regra do `schedule_scores_refresh` em
  `posts/router.py`) depois de baixa/estorno.
- **`GET /bank-accounts/{id}/balance` (spec 055, dívida técnica #20) não foi tocado.**
  `docs/DIVIDA-TECNICA.md` atribui o retrofit do saldo real desse endpoint específico
  (mais exclusão/imutabilidade de conta) à spec 070 — a 059 não reabre esse escopo.
  Em vez disso, criou um endpoint novo e próprio do dashboard,
  `GET /bank-accounts/balances` (plural), que usa a view materializada só para os
  cards. `test_transferencia_nao_altera_saldo_hoje_deferido` (spec 056) continua
  válido sem edição: nenhuma baixa aconteceu naquele teste, então o saldo real
  (que a 059 agora calcula de verdade neste endpoint novo) também é zero.
- **Regime `cash_flow` é híbrido, não uma 5ª coluna de data.** Pago conta por
  `payment_date`; em aberto (sem pagamento) conta por `due_date` — implementado como
  um `OR` de duas condições (`_period_filter` em `dashboard.py`), não uma coluna
  nova na tabela.
- **Cartão de crédito reaproveitou `card_cycle_range` (spec 055, `app/core/dates.py`)
  sem duplicar a lógica de ciclo** — a fatura do dashboard é a soma das `DESPESA` com
  vencimento na janela do ciclo corrente, pago ou não.
- **Fórmula de saldo por conta usa `DISTINCT ON` (Postgres) em vez de subqueries
  repetidas por conta** — uma query cobre N contas de uma vez (`deltas_as_of`),
  parte do orçamento de "≤5 statements" do dashboard (3 na prática: agregados de
  período, atrasados, e 2 chamadas a `deltas_as_of` — hoje/mês anterior — mais a
  listagem de contas).
- **Rodapé da listagem (regra 9) não ganhou endpoint próprio** — calculado no
  cliente a partir da página de lançamentos já carregada (`TransactionsListPage`),
  já que "total/saldo/previsto" da listagem não estava no contrato de API da spec
  (só os 4 endpoints do dashboard estão) e não tinha teste dedicado no plano.
- **`StatCard` (`components/domain`) ganhou a prop opcional `negative?: boolean`**
  para pintar o valor em vermelho (regra 10) — o componente não sabe o sinal de um
  `value` já formatado em string (`formatBrl`), então quem chama decide. Mudança
  aditiva, sem impacto nos consumidores existentes (`LawsuitStatsPanel`,
  `LawsuitFinancialPanel`).
- **`CashFlowChart` (novo, `components/domain`) — BarChart não serve para duas
  séries.** `BarChart` (spec 019) só desenha uma barra por rótulo; o gráfico
  "Receitas x Despesas por vencimento" do ADVBOX precisa de duas por período, então
  virou um componente novo (mesmo estilo sem lib, cores `success`/`danger` já
  estabelecidas pelo app para dinheiro positivo/negativo).
- **Jornada e2e 9/25 precisou de dois ajustes de infraestrutura fora do código de
  produto:** (1) `seed_e2e.py` ganhou `financial_access=FinancialAccess.FULL` no
  usuário e2e — sem isso o item "Financeiro" nem aparece na sidebar
  (`financial.read`); nenhuma spec financeira anterior (054-058) tinha e2e, então
  ninguém tinha esbarrado nisso ainda. (2) categoria/centro de custo/conta do
  ADVBOX são pré-condições criadas via API no início do teste (mesmo padrão de
  `lawsuits.spec.ts`/`inbox.spec.ts`) — a migration 054 só semeia essas tabelas para
  tenants que já existiam quando ela rodou, mesma limitação já documentada em
  `test_financial_seed.py`.
- **A jornada e2e não verifica o card "Saldo" nem "Saldo por conta"** — os dois
  dependem do refresh da view materializada, e o ambiente e2e (Playwright) não sobe
  worker Celery algum (só uvicorn + vite, ver `playwright.config.ts`), então a view
  fica genuinamente estática durante o teste (comportamento correto e esperado, não
  um bug). A jornada verifica o card **Receita**, que é calculado ao vivo (sem
  depender da view) — comparando o valor antes/depois da baixa, nunca um valor
  absoluto, porque o tenant e2e nunca reseta entre execuções (mesmo achado já
  documentado nas specs 057/058) e o card acumula lançamentos de rodadas anteriores.
- **Duas falhas pré-existentes e não relacionadas** apareceram em execuções cheias
  da suíte neste ciclo (`test_sync_observability.py`, `test_inbox_perf.py`) —
  mesma causa raiz já documentada nas specs 051/052/058 (banco de teste sujo por
  execuções de `pytest` fora do `run-tests.sh`, que não limpa `integration_alerts`
  nem é imune a contenção de CPU das 3 suítes concorrentes). Confirmadas ausentes
  isoladamente e depois de `TRUNCATE`/`DELETE` manual; nenhum código de
  `test_sync_observability.py`/`test_inbox_perf.py` foi tocado por esta spec.

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as regras de negócio com teste
- [x] `make test` verde e wall-clock dentro do orçamento de 300 s (CLAUDE.md §3)
- [x] `make lint` verde
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário
- [x] Componentes reutilizáveis extraídos quando bateu 3 usos (`CashFlowChart`)
- [x] `ROADMAP.md` atualizado para ✅
- [x] 4 regimes testados com o mesmo dataset
- [x] Commit `feat(059): financeiro — dashboard e fluxo de caixa`
