# 052 — CRM: estagnação e métricas

**Fase:** 5 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 051 · **Status:** ⬜ pendente

---

## 1. Objetivo

Processo parado é dinheiro parado e cliente insatisfeito. Aqui o funil passa a apontar
sozinho o que travou.

## 2. Escopo

- Cálculo de estagnação por etapa
- Destaque visual do card estagnado
- Filtro: todos / só estagnados / só em andamento
- Cards de topo do CRM
- Job diário de recálculo

## 3. Fora de escopo

- Workflow ao mover → 053 · BI de tempo → 076 · Detecção de risco por IA → 089

## 4. Modelo de dados

```sql
ALTER TABLE lawsuits
  ADD COLUMN is_stagnant BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN stagnant_since DATE;

CREATE INDEX ix_lawsuits_stagnant ON lawsuits (tenant_id, is_stagnant)
  WHERE is_stagnant AND NOT is_archived;
```
Migration `052_stagnation.py`.

## 5. Contratos de API

| Método | Rota |
|---|---|
| GET | `/api/v1/crm/board?display_stagnant=all\|stagnant\|active` |
| GET | `/api/v1/crm/stats` |
| POST | `/api/v1/crm/recalculate-stagnation` (ADMINISTRADOR, manual) |

`stats`: `total_lawsuits`, `received_this_month`, `total_value`, `stagnant_count`,
`stagnant_value`, `by_step[]`.

## 6. Front-end

**Reutiliza:** `StatCard`, `FilterBar`, `KanbanCard`
**Cria:** `StagnantBadge`, `CrmStatsBar`, `StagnationTooltip`
**Rota:** topo de `/crm`

## 7. Regras de negócio

1. Estagnado quando a etapa tem `enable_stagnant_days = true` **e** o processo está nela há mais
   dias do que `stagnant_days`, contados a partir de `stage_entered_at`.
2. Etapa sem estagnação configurada nunca marca — a regra é da etapa, não global.
3. O cálculo considera **dias corridos**, não úteis. É indicador de gestão, não prazo processual.
4. Job diário às 3h recalcula todo o tenant; mover o processo recalcula na hora.
5. `stagnant_since` guarda quando entrou em estagnação, para ordenar por gravidade.
6. Processo arquivado nunca é estagnado.
7. Card estagnado mostra badge com os dias e tooltip explicando a regra da etapa.
8. `stagnant_value` soma o valor da causa dos estagnados — é o número que dói.
9. Recálculo manual é limitado a uma vez por hora por tenant.
10. Mudar `stagnant_days` da etapa recalcula os processos dela em background.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | marca estagnado ao passar do limite | ~0,4 s |
| integração | etapa sem configuração nunca marca | ~0,3 s |
| integração | mover reseta `stage_entered_at` e desmarca | ~0,4 s |
| integração | arquivado nunca estagna | ~0,2 s |
| integração | job diário recalcula o tenant | ~0,4 s |
| integração | mudar `stagnant_days` recalcula a etapa | ~0,4 s |
| integração | filtro dos 3 modos | ~0,4 s |
| integração | `stagnant_value` soma correto | ~0,3 s |
| integração | recálculo manual 2× em 1 h → 429 | ~0,3 s |
| frontend | badge mostra dias e tooltip | ~0,4 s |

**Total:** ~3,5 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Commit `feat(052): CRM — estagnação e métricas`
