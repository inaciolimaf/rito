# 076 — BI: Tempo e Honorários

**Fase:** 7 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 075 · **Status:** ⬜ pendente

---

## 1. Objetivo

Quanto tempo se investe e quanto valor se gera em cada processo, ao longo do ciclo completo.
Responde a pergunta que define precificação: "esse tipo de ação compensa?".

## 2. Escopo

- Média de honorários por processo e média mensal
- **Tempo perdido**: meses de processo sem receita
- Quatro ciclos: prospecção, produção, execução, rotação completa
- Tempo médio por fase e por grupo de ação
- Rentabilidade mensal por tipo de ação
- Relatórios filtráveis

## 3. Fora de escopo

- Custos → 077 · Precificação sugerida por IA → 089

## 4. Modelo de dados

```sql
CREATE MATERIALIZED VIEW bi_lawsuit_cycles AS
SELECT l.tenant_id, l.id AS lawsuit_id, l.action_group_id, l.lawsuit_type_id,
       l.outcome, l.closure_date, l.fees_value,
       -- prospecção: criação → fechamento do contrato
       (l.closure_date - l.created_at::date) AS prospecting_days,
       -- produção: fechamento → trânsito em julgado
       (l.transit_date - l.closure_date) AS production_days,
       -- execução: trânsito → arquivamento
       (l.archived_date - l.transit_date) AS execution_days,
       -- rotação completa: criação → arquivamento
       (l.archived_date - l.created_at::date) AS full_cycle_days,
       COALESCE((SELECT SUM(t.amount) FROM transactions t
                 WHERE t.lawsuit_id = l.id AND t.kind='RECEITA'
                   AND NOT t.is_internal AND t.payment_date IS NOT NULL), 0) AS revenue
FROM lawsuits l WHERE l.closure_date IS NOT NULL;
CREATE UNIQUE INDEX ux_bi_cycles ON bi_lawsuit_cycles (tenant_id, lawsuit_id);
```
Migration `076_bi_cycles.py`. Refresh a cada 8 h.

## 5. Contratos de API

| Método | Rota |
|---|---|
| GET | `/api/v1/bi/time-fees?outcome=&from=&to=&action_group_id=` |
| GET | `/api/v1/bi/time-fees/by-group` |
| GET | `/api/v1/bi/time-fees/by-type?lawsuit_type_id=` |
| GET | `/api/v1/bi/time-fees/lost-time` |

## 6. Front-end

**Reutiliza:** `StatCard`, `BarChart`, `DataTable`, `FilterBar`, `MoneyField`
**Cria:** `TimeFeesPanel`, `CycleBarChart` (4 cores: verde prospecção, azul claro produção,
azul escuro execução, vermelho rotação), `LostTimeCard`, `ProfitabilityTable`
**Rota:** `/reports?tab=time-fees`

## 7. Regras de negócio

1. Os 4 ciclos, em dias:
   - **Prospecção:** criação → `closure_date`
   - **Produção:** `closure_date` → `transit_date`
   - **Execução:** `transit_date` → `archived_date`
   - **Rotação completa:** criação → `archived_date`
2. Ciclo com data faltando fica **nulo**, não zero. Zero significa "no mesmo dia" e é diferente de "não sei".
3. Média de honorários = soma de `fees_value` ÷ processos no filtro.
4. Média mensal = honorários ÷ meses de duração do processo. Processo longo e barato derruba a média — é justamente o que o indicador quer mostrar.
5. **Tempo perdido** = soma dos meses de processos com `revenue = 0` e ciclo maior que zero.
6. `revenue` vem de lançamentos de receita **pagos**, não internos, vinculados ao processo.
7. Filtro por resultado (todos, ganhos, perdidos) recalcula tudo.
8. Rentabilidade mensal por tipo = média de (`fees_value` ÷ meses) dos processos daquele tipo.
9. Tipo com menos de 5 processos exibe aviso de amostra pequena.
10. Gráfico por grupo mostra os 4 ciclos lado a lado.
11. Exige ADMINISTRADOR ou GESTOR e `financial_access ≥ READ_ONLY` — a aba mostra dinheiro.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| unit | **os 4 ciclos com datas completas** | ~0,3 s |
| unit | ciclo com data faltando é nulo, não zero | ~0,2 s |
| integração | média de honorários por processo | ~0,3 s |
| integração | média mensal penaliza processo longo e barato | ~0,4 s |
| integração | tempo perdido soma só os sem receita | ~0,4 s |
| integração | `revenue` ignora não pago e interno | ~0,4 s |
| integração | filtro por resultado recalcula | ~0,4 s |
| integração | rentabilidade por tipo | ~0,4 s |
| integração | menos de 5 processos → aviso | ~0,2 s |
| integração | `financial_access = NONE` → 403 | ~0,3 s |
| frontend | gráfico com as 4 cores dos ciclos | ~0,4 s |

**Total:** ~3,7 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Nulo distinguido de zero · Dupla permissão testada · Commit `feat(076): BI — tempo e honorários`
