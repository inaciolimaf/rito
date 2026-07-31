# 051 — CRM: board Kanban

**Fase:** 5 · **Tipo:** feature · **Orçamento:** +7 s
**Depende de:** 027, 007 · **Status:** ⬜ pendente

---

## 1. Objetivo

Visão de funil: processos como cards, colunas por fase, arrastar para avançar. É a tela do
sócio que quer ver onde o dinheiro está parado.

## 2. Escopo

- `KanbanBoard` genérico e reutilizável
- Colunas pelas 9 fases
- Drag & drop com persistência otimista
- Card com partes, tipo, valor, responsável, tempo na etapa
- Virtualização para volume
- Ação em massa "alterar fase"

## 3. Fora de escopo

- Estagnação e métricas → 052 · Workflow ao mover → 053

## 4. Modelo de dados

```sql
CREATE TABLE lawsuit_stage_history (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  lawsuit_id UUID NOT NULL REFERENCES lawsuits(id) ON DELETE CASCADE,
  from_stage_id UUID REFERENCES stages(id),
  to_stage_id UUID NOT NULL REFERENCES stages(id),
  changed_by UUID NOT NULL REFERENCES users(id),
  changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_stage_history ON lawsuit_stage_history (lawsuit_id, changed_at DESC);

ALTER TABLE lawsuits ADD COLUMN stage_entered_at TIMESTAMPTZ NOT NULL DEFAULT now();
```
Migration `051_stage_history.py`. `stage_entered_at` é atualizada por trigger — é a base do
tempo na etapa (052) e do BI de tempo (076).

## 5. Contratos de API

| Método | Rota |
|---|---|
| GET | `/api/v1/crm/board?<mesmos filtros de /lawsuits>&limit_per_column=50` |
| POST | `/api/v1/lawsuits/{id}/move-stage` → `{stage_id}` |
| POST | `/api/v1/lawsuits/bulk/move-stage` → `{lawsuit_ids[], stage_id}` |
| GET | `/api/v1/crm/board/column/{step_id}?cursor=` — paginação da coluna |

## 6. Front-end

**Reutiliza:** `FilterBar`, `EmptyState`, `ConfirmDialog`
**Cria:** `KanbanBoard<T>` (genérico), `KanbanColumn`, `KanbanCard`, `LawsuitCard`, `CrmPage`
**Rota:** `/crm`

`KanbanBoard` é genérico de propósito — recebe colunas, itens, `onMove` e um render de card.
Não conhece processo.

## 7. Regras de negócio

1. Colunas são as **9 fases**, sempre todas visíveis, mesmo vazias.
2. Card exibe: partes (2 + contador), tipo de ação, valor da causa, responsável, tempo na etapa.
3. Arrastar entre colunas move para a **primeira etapa** da fase destino, por `position`.
4. Movimento é otimista: a UI atualiza na hora e reverte se a API falhar.
5. Toda mudança de etapa grava em `lawsuit_stage_history` — inclusive as feitas fora do Kanban.
6. `stage_entered_at` é atualizado por trigger a cada mudança.
7. Coluna carrega 50 cards e pagina por scroll; o contador mostra o total real.
8. Filtros do CRM são os mesmos de `/lawsuits` — mesmo `ListQueryBuilder`.
9. Ação em massa é transacional.
10. Colaborador move só processos onde é responsável; ADMINISTRADOR move qualquer um.
11. Board com mais de 2.000 cards no total sugere refinar o filtro, em vez de renderizar tudo.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | board retorna 9 colunas, inclusive vazias | ~0,4 s |
| integração | mover grava histórico | ~0,4 s |
| integração | mover vai para a primeira etapa da fase | ~0,3 s |
| integração | trigger atualiza `stage_entered_at` | ~0,3 s |
| integração | mudança fora do Kanban também grava histórico | ~0,3 s |
| integração | Colaborador não move processo alheio → 403 | ~0,3 s |
| integração | ação em massa é transacional | ~0,4 s |
| integração | paginação por coluna | ~0,4 s |
| integração | **budget: board ≤ 3 statements** | ~0,4 s |
| frontend | `KanbanBoard` genérico com dados falsos | ~0,5 s |
| frontend | drag & drop chama `onMove` | ~0,5 s |
| frontend | falha da API reverte a UI | ~0,4 s |
| e2e | **jornada 8/25:** arrastar card e ver a fase mudar | ~4 s |

**Total:** ~8,6 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · `KanbanBoard` sem conhecimento de domínio · Commit `feat(051): CRM — board Kanban`
