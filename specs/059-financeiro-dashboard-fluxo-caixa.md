# 059 — Financeiro: dashboard e fluxo de caixa

**Fase:** 5 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 058 · **Status:** ⬜ pendente

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

*(preencher)*

## 10. Definição de pronto

Checklist padrão · 4 regimes testados com o mesmo dataset · Commit `feat(059): financeiro — dashboard e fluxo de caixa`
