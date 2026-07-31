# 077 — BI: Custos

**Fase:** 7 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 076 · **Status:** ⬜ pendente

---

## 1. Objetivo

Quanto custa gerar, produzir e concluir um processo. Fecha o quadrado do BI: com 076 (receita e
tempo) e esta (custo), o escritório sabe a margem real por tipo de ação.

## 2. Escopo

- CAC — custo de aquisição de cliente
- Custo médio em produção, execução e rotação completa
- **Custo por ponto** (esforço do Taskscore)
- Gráfico de tempo por etapa
- Rateio de custo fixo por processo
- Considera processos **em andamento**, diferente das outras abas

## 3. Fora de escopo

- Precificação sugerida → 089 · Folha de pagamento detalhada (fora do escopo)

## 4. Modelo de dados

```sql
CREATE MATERIALIZED VIEW bi_cost_allocation AS
WITH monthly_fixed AS (
  SELECT tenant_id, competence,
         SUM(amount) FILTER (WHERE c.dre_group_id IN (2,3,5,7)) AS fixed_cost,
         SUM(amount) FILTER (WHERE c.dre_group_id = 8)          AS marketing_cost
  FROM transactions t JOIN financial_categories c ON c.id = t.category_id
  WHERE t.kind='DESPESA' AND NOT t.is_internal
  GROUP BY 1,2
),
monthly_points AS (
  SELECT tenant_id, date_trunc('month', completed_at)::date AS competence,
         SUM(points_earned) AS points
  FROM post_users WHERE completed_at IS NOT NULL GROUP BY 1,2
)
SELECT f.tenant_id, f.competence, f.fixed_cost, f.marketing_cost,
       p.points,
       CASE WHEN p.points > 0 THEN f.fixed_cost / p.points END AS cost_per_point
FROM monthly_fixed f LEFT JOIN monthly_points p USING (tenant_id, competence);
CREATE UNIQUE INDEX ux_bi_cost ON bi_cost_allocation (tenant_id, competence);
```
Migration `077_bi_costs.py`. Refresh a cada 8 h.

## 5. Contratos de API

| Método | Rota |
|---|---|
| GET | `/api/v1/bi/costs?outcome=&from_year=&to_year=` |
| GET | `/api/v1/bi/costs/cac?period=` |
| GET | `/api/v1/bi/costs/per-point?period=` |
| GET | `/api/v1/bi/costs/by-stage` |

## 6. Front-end

**Reutiliza:** `StatCard`, `BarChart`, `DataTable`, `FilterBar`, `MoneyField`
**Cria:** `CostsPanel`, `CostPerStageChart`, `CacCard`, `CostPerPointCard`,
`AllocationExplainer` (tooltip explicando o rateio)
**Rota:** `/reports?tab=costs`

## 7. Regras de negócio

1. **CAC** = despesas do grupo 8 (marketing e comercial) ÷ clientes novos no período.
2. **Custo por ponto** = custo fixo do mês ÷ pontos do Taskscore concluídos no mês. É a métrica
   que traduz esforço em dinheiro.
3. Custo fixo = grupos DRE 2 (folha), 3 (encargos), 5 (fixas) e 7 (bancárias).
4. Custo direto do processo = despesas lançadas com `lawsuit_id` preenchido.
5. **Custo alocado** do processo = custo direto + (pontos das tarefas do processo × custo por ponto do mês).
6. Diferente das outras abas, esta **considera processos em andamento** — custo acontece antes do fechamento.
7. Filtro por intervalo de anos usa `archived_date`; processo sem arquivamento entra se estiver dentro do período por `created_at`.
8. Mês sem pontos → custo por ponto nulo, não infinito. Exibe "—".
9. Mês sem custo fixo → CAC nulo, não zero.
10. Gráfico de tempo por etapa usa as 4 cores de 076, mantendo consistência visual.
11. Rateio é **aproximação** — o tooltip explica a fórmula, para ninguém tratar como contabilidade.
12. Exige ADMINISTRADOR ou GESTOR e `financial_access ≥ READ_ONLY`.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | CAC = marketing ÷ clientes novos | ~0,4 s |
| integração | **custo por ponto = fixo ÷ pontos** | ~0,4 s |
| integração | custo fixo soma só os grupos 2, 3, 5, 7 | ~0,4 s |
| integração | custo direto por `lawsuit_id` | ~0,3 s |
| integração | custo alocado soma direto + rateio | ~0,4 s |
| integração | processo em andamento entra no cálculo | ~0,3 s |
| integração | mês sem pontos → "—", não infinito | ~0,2 s |
| integração | mês sem custo → CAC nulo | ~0,2 s |
| integração | interno e transferência fora do custo | ~0,3 s |
| integração | dupla permissão | ~0,3 s |
| frontend | tooltip explica a fórmula do rateio | ~0,3 s |

**Total:** ~3,5 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Divisão por zero tratada em todos os indicadores · Commit `feat(077): BI — custos`
