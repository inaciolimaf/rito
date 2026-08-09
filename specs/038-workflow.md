# 038 — Workflow

**Fase:** 3 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 034, 015 · **Status:** ✅ concluída

---

## 1. Objetivo

Sequência padronizada de tarefas com responsável e prazo, disparada ao mover o processo de
etapa. É o que transforma rotina em processo repetível — e a base do motor de automação (092).

## 2. Escopo

- Tabelas `workflows` e `workflow_steps`
- Editor de sequência com reordenação
- Disparo ao mudar de etapa (com confirmação)
- **Cálculo de dias úteis** com feriados nacionais
- Aplicação manual a um processo

## 3. Fora de escopo

- Gatilhos além de mudança de etapa → 092
- Decisão por LLM → 094

## 4. Modelo de dados

```sql
CREATE TABLE workflows (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  name TEXT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);

CREATE TABLE workflow_steps (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
  position SMALLINT NOT NULL,
  task_type_id UUID NOT NULL REFERENCES task_types(id),
  user_id UUID REFERENCES users(id),        -- NULL = responsável do processo
  days_offset SMALLINT,                     -- dias úteis a partir do disparo
  UNIQUE (workflow_id, position)
);

CREATE TABLE holidays (                      -- global
  date DATE PRIMARY KEY, name TEXT NOT NULL, is_national BOOLEAN NOT NULL DEFAULT true
);

ALTER TABLE stages
  ADD CONSTRAINT fk_stages_workflow
  FOREIGN KEY (suggested_workflow_id) REFERENCES workflows(id);
```
Migration `038_workflows.py` + seed de feriados nacionais 2026–2030.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/workflows?status=&q=` | autenticado |
| POST/PUT/DELETE | `/api/v1/workflows[/{id}]` | GESTOR |
| POST | `/api/v1/workflows/{id}/preview` | autenticado — `{lawsuit_id}` → tarefas que seriam criadas |
| POST | `/api/v1/workflows/{id}/apply` | COLABORADOR — `{lawsuit_id}` |
| GET | `/api/v1/holidays?year=` | autenticado |

`PUT /workflows/{id}` recebe `steps[]` completo e reconcilia.

## 6. Front-end

**Reutiliza:** `DataTable`, `FormModal`, `EntityPicker`, `ConfirmDialog`
**Cria:** `WorkflowEditor` (lista ordenável de etapas), `WorkflowStepRow`
(tarefa + responsável + dias), `WorkflowPreviewDialog`
**Rota:** `/settings/workflows`

## 7. Regras de negócio

1. Etapa do workflow exige `task_type_id`; responsável e prazo são opcionais.
2. `user_id` nulo → a tarefa vai para o **responsável do processo** no momento da aplicação.
3. `days_offset` conta **dias úteis** a partir da data de disparo, pulando sábado, domingo e feriado nacional.
4. `days_offset = 0` significa hoje; nulo significa sem prazo.
5. Aplicar cria todas as tarefas em **uma transação** — falha em uma, nenhuma é criada.
6. Preview mostra exatamente o que seria criado, sem persistir nada.
7. Mover o processo para etapa com `suggested_workflow_id` **sugere** e pede confirmação; nunca aplica sozinho.
8. Aplicar o mesmo workflow duas vezes no mesmo processo pede confirmação extra.
9. Excluir workflow não afeta tarefas já criadas.
10. Etapa com tipo de tarefa inativo é pulada, com aviso.
11. Reordenar é transacional.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| unit | **dias úteis pulando fim de semana** (tabela) | ~0,2 s |
| unit | dias úteis pulando feriado nacional | ~0,2 s |
| unit | `days_offset = 0` é hoje | ~0,1 s |
| integração | CRUD com etapas reconciliadas | ~0,4 s |
| integração | aplicar cria N tarefas com datas certas | ~0,5 s |
| integração | responsável nulo herda o do processo | ~0,3 s |
| integração | aplicação é transacional | ~0,4 s |
| integração | preview não persiste | ~0,3 s |
| integração | tipo inativo é pulado com aviso | ~0,3 s |
| integração | excluir workflow não apaga tarefas | ~0,3 s |
| integração | Colaborador não cria workflow → 403 | ~0,2 s |
| frontend | editor reordena etapas | ~0,5 s |
| frontend | preview lista as tarefas | ~0,4 s |

**Total:** ~4,1 s

## 9. Descobertas

1. **`Base` injeta `id` UUID como PK em toda tabela** — para `holidays` (PK = `date`,
   modelo da spec) o atributo herdado foi remapeado para a coluna `date` (mesmo padrão
   do `Court` com seu código inteiro). Coluna chamada `date` dispara
   `MappedAnnotationError` se a anotação usar o tipo `date` sem alias.
2. **Apply não reusa `PostService.create`**: o duplicate-check de posts (mesmo tipo +
   data + responsáveis) quebraria a reaplicação permitida pela regra 8 e workflows com
   etapas repetidas do mesmo tipo. A criação vai direto pelo `PostRepository` na sessão
   da request — a atomicidade da regra 5 sai de graça (exceção → rollback total).
3. **`already_applied` é heurística** (existe post do processo com algum dos tipos do
   workflow): posts não guardam `workflow_id` — fora do modelo de dados da spec. Se
   falsos positivos incomodarem na prática, candidato a coluna na 040.
4. **`GET /workflows/{id}`** nasceu além da tabela de contratos (só list/preview/apply):
   o editor precisa das etapas completas para editar.
5. **Seed de feriados cobre 2026–2030** (móveis derivados da Páscoa; Consciência Negra
   inclusa, feriado nacional desde 2024). Em 2030+ a tabela precisa de novo seed —
   dívida anotada para a spec 086 (prazos), que já reutiliza `add_business_days`.
6. **Feriado municipal/estadual ficou fora**: a tabela aceita (`is_national`), mas o
   cálculo só considera nacionais — igual ao ADVBOX, que trata suspenso de prazo por
   feriado nacional. Municipal entra quando houver demanda real.

## 10. Definição de pronto

- [x] Checklist padrão (lint verde, testes da spec escritos e verdes, migration `038_workflows`)
- [x] Calculadora de dias úteis isolada e reutilizável (`domain/workflows/business_days.py` — a 086 vai usar)
- [x] Isolamento entre tenants testado (tabelas novas com RLS)
- [x] `make test` verde em **154 s** (orçamento 300 s) — 578 backend / 120 frontend / 7 e2e
- [x] Commit `feat(038): workflow`
