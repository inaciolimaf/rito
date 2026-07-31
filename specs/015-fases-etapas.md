# 015 — Fases e etapas

**Fase:** 1 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 014 · **Status:** ⬜ pendente

---

## 1. Objetivo

O funil processual. **Fase** (`step`) é o macro-estágio — 9 valores fixos que viram as colunas
do Kanban. **Etapa** (`stage`) é o estado detalhado dentro da fase, configurável pelo escritório,
com regra de estagnação própria.

## 2. Escopo

- Tabela `steps`: 9 fases fixas, seed imutável (sem CRUD)
- Tabela `stages`: 59 etapas padrão, CRUD completo
- Configuração de estagnação por etapa (`enable_stagnant_days`, `stagnant_days`)
- Campo de workflow sugerido ao mover para a etapa (FK preenchida em 038)
- Transferência em lote antes de excluir
- Tela `Configurações > Etapas`

## 3. Fora de escopo

- Kanban → 051
- Motor de workflow → 038
- Cálculo efetivo de estagnação → 052

## 4. Modelo de dados

```sql
CREATE TABLE steps (            -- global, imutável
  id SMALLINT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  position SMALLINT NOT NULL UNIQUE
);

CREATE TABLE stages (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  step_id SMALLINT NOT NULL REFERENCES steps(id),
  name TEXT NOT NULL,
  position INTEGER NOT NULL DEFAULT 0,
  enable_stagnant_days BOOLEAN NOT NULL DEFAULT false,
  stagnant_days INTEGER,
  suggested_workflow_id UUID,      -- FK adicionada em 038
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name),
  CHECK (NOT enable_stagnant_days OR stagnant_days > 0)
);
CREATE INDEX ix_stages_step ON stages (step_id);
```
Migration `015_steps_stages.py`.

**Seed de fases (9, nesta ordem):** Marketing · Negociação · Consultoria · Administrativo ·
Judicial · Recursal · Execução/cobrança · Rh/financeiro · Arquivamento

**Seed de etapas (59):** a lista completa está em
`docs/ADVBOX-ESPECIFICACAO-COMPLETA.md` §3.2. Cada etapa é semeada na fase correspondente.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/steps` | autenticado |
| GET | `/api/v1/stages?step_id=&status=&q=` | autenticado |
| POST/PUT/DELETE | `/api/v1/stages[/{id}]` | GESTOR |
| POST | `/api/v1/stages/reorder` | GESTOR — `{stage_ids[]}` |
| POST | `/api/v1/stages/transfer` | GESTOR — `{from_id, to_id}` |

## 6. Front-end

**Reutiliza:** `DataTable`, `FilterBar`, `FormModal`, `TransferBeforeDeleteDialog`
**Cria:** `StageForm` (nome, fase, estagnação, workflow), `StageReorderList` (drag & drop)
**Rota:** `/settings/stages`

Colunas: Etapa · Classificação (fase) · Estagnação · Cadastro

## 7. Regras de negócio

1. As 9 fases são **imutáveis**: não há POST, PUT nem DELETE em `/steps`.
2. Etapa pertence a exatamente uma fase.
3. `enable_stagnant_days = true` exige `stagnant_days > 0` (constraint no banco).
4. Excluir etapa em uso exige transferência.
5. Ordenação é por `position` dentro da fase; reordenar é transacional.
6. Nome único por tenant, comparação sem acento.
7. Inativar mantém histórico e remove dos seletores.
8. Etapa não pode mudar de fase se houver processo nela — exige transferência.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | fases são somente leitura (POST → 405) | ~0,2 s |
| integração | CRUD de etapas | ~0,4 s |
| integração | estagnação sem dias → 422 | ~0,2 s |
| integração | excluir etapa em uso → 409 | ~0,3 s |
| integração | reordenação persiste e é transacional | ~0,4 s |
| integração | mudar fase com processo na etapa → 409 | ~0,3 s |
| integração | RLS entre tenants | ~0,3 s |
| unit | seed das 59 etapas mapeia a fase certa | ~0,2 s |
| frontend | `StageForm` condiciona dias à estagnação | ~0,4 s |

**Total:** ~2,7 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · 9 fases + 59 etapas semeadas · Commit `feat(015): fases e etapas`
