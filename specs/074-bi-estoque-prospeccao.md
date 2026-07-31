# 074 — BI: Estoque e Prospecção

**Fase:** 7 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 072 · **Status:** ⬜ pendente

---

## 1. Objetivo

Primeira das quatro abas de Business Intelligence: o funil comercial. Quantas oportunidades
entraram, quantas viraram contrato, e quanto do estoque está parado.

## 2. Escopo

- Indicadores: oportunidades do mês, processos ativos, arquivados, parados +120 dias, fechamentos do mês, em atendimento
- Evolução de fechamentos nos últimos 6 meses
- Resumo da carteira por fase e período
- Taxa de conversão por grupo de ação
- Relatórios filtráveis no rodapé

## 3. Fora de escopo

- Safra → 075 · Tempo → 076 · Custos → 077

## 4. Modelo de dados

```sql
CREATE MATERIALIZED VIEW bi_pipeline_monthly AS
SELECT l.tenant_id, date_trunc('month', l.created_at)::date AS month,
       l.action_group_id,
       COUNT(*) AS opportunities,
       COUNT(*) FILTER (WHERE l.closure_date IS NOT NULL) AS closed,
       COUNT(*) FILTER (WHERE l.archived_date IS NOT NULL) AS archived,
       SUM(l.case_value) AS total_case_value,
       SUM(l.fees_value) FILTER (WHERE l.closure_date IS NOT NULL) AS closed_fees
FROM lawsuits l WHERE NOT l.is_archived GROUP BY 1,2,3;
CREATE UNIQUE INDEX ux_bi_pipeline ON bi_pipeline_monthly (tenant_id, month, action_group_id);

CREATE INDEX ix_lawsuits_idle_120 ON lawsuits (tenant_id, last_movement_at)
  WHERE NOT is_archived;
```
Migration `074_bi_pipeline.py`. Refresh a cada **8 horas**, como no ADVBOX.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/bi/pipeline?from=&to=&action_group_id=` | ADMINISTRADOR |
| GET | `/api/v1/bi/pipeline/conversion?period=` | ADMINISTRADOR |
| GET | `/api/v1/bi/pipeline/portfolio?group_by=step\|period` | ADMINISTRADOR |

## 6. Front-end

**Reutiliza:** `StatCard`, `BarChart`, `DonutChart`, `DataTable`, `FilterBar`
**Cria:** `BiTabs` (navegação entre as 4 abas), `PipelinePanel`, `ConversionFunnel`,
`SixMonthTrend`, `StaleWarning`, `BiRefreshIndicator`
**Rota:** `/reports?tab=pipeline`

## 7. Regras de negócio

1. **Oportunidades do mês** = processos criados no mês, qualquer fase.
2. **Processos ativos** = não arquivados, nas fases administrativa, consultoria, judicial, recursal ou execução.
3. **Arquivados** = com `archived_date` preenchida.
4. **Parados +120 dias** = `last_movement_at` mais antigo que 120 dias **ou** nulo, entre os ativos. É o indicador de alerta da aba.
5. **Fechamentos do mês** = `closure_date` no mês, com variação vs mês anterior e série de 6 meses.
6. **Em atendimento** = processos nas fases marketing, negociação ou consultoria.
7. **Taxa de conversão** = fechados ÷ oportunidades, por grupo de ação, no período.
8. Gráficos vêm da view materializada (até 8 h de defasagem, sinalizada). Os **relatórios do rodapé são tempo real**.
9. Aba exige ADMINISTRADOR ou GESTOR.
10. Grupo sem movimento aparece zerado, não some.
11. Divisão por zero na conversão → exibe "—", nunca `NaN` ou 0%.
12. Aviso claro: qualidade do indicador depende do CRM alimentado.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | 6 indicadores com seed determinístico | ~0,6 s |
| integração | parados +120 dias inclui `last_movement_at` nulo | ~0,4 s |
| integração | fechamentos com variação e série de 6 meses | ~0,4 s |
| integração | conversão por grupo | ~0,4 s |
| integração | conversão com zero oportunidades → "—" | ~0,2 s |
| integração | gráfico usa a view; relatório é tempo real | ~0,4 s |
| integração | Colaborador → 403 | ~0,2 s |
| integração | grupo sem movimento aparece zerado | ~0,2 s |
| integração | refresh da view atualiza os números | ~0,4 s |
| frontend | indicador de defasagem visível | ~0,3 s |

**Total:** ~3,5 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Divisão por zero tratada · Commit `feat(074): BI — estoque e prospecção`
