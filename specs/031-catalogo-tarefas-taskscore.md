# 031 — Catálogo de tarefas e Taskscore

**Fase:** 3 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 015 · **Status:** ✅ concluída

---

## 1. Objetivo

O Taskscore é o diferencial do produto: cada tipo de tarefa vale pontos calculados a partir de
**complexidade × tempo médio**. Concluir tarefa gera pontuação, pontuação vira ranking e meta.
Aqui construímos o catálogo e a calculadora.

## 2. Escopo

- Tabela `task_types` com as 152 tarefas padrão
- Enums de complexidade (5) e tempo médio (5)
- **Matriz de pontuação** determinística com sugestão editável
- 3 tarefas sistêmicas protegidas
- Inativar, restaurar e transferir em lote
- Tela `Configurações > Tarefas`

## 3. Fora de escopo

- Tarefas em si → 032 · Ranking e metas → 039 · Workflow → 038

## 4. Modelo de dados

```sql
CREATE TYPE task_complexity AS ENUM ('SIMPLES','MEDIA','MEDIA_ALTA','ALTA','ALTISSIMA');
CREATE TYPE task_duration   AS ENUM ('MIN_8','MIN_15','MIN_30','HOUR_1','HOUR_2_PLUS');

CREATE TABLE task_types (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  name TEXT NOT NULL,
  step_id SMALLINT REFERENCES steps(id),      -- NULL = todas as fases
  complexity task_complexity,
  duration task_duration,
  reward INTEGER NOT NULL DEFAULT 0,          -- pontos
  show_in_schedule BOOLEAN NOT NULL DEFAULT false,
  is_system BOOLEAN NOT NULL DEFAULT false,   -- protegida
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);
CREATE INDEX ix_task_types_step ON task_types (tenant_id, step_id);
```
RLS ligado. Migration `031_task_types.py`.

**Matriz de pontuação sugerida** (`complexidade × duração`):

| | 8 min | 15 min | 30 min | 1 h | +2 h |
|---|---|---|---|---|---|
| **Simples** | 5 | 8 | 15 | 30 | 60 |
| **Média** | 10 | 15 | 30 | 60 | 120 |
| **Média alta** | 15 | 25 | 45 | 90 | 180 |
| **Alta** | 20 | 35 | 70 | 150 | 280 |
| **Altíssima** | 30 | 50 | 100 | 200 | 400 |

Ancorada nos dois exemplos oficiais do ADVBOX: simples/15 min = 8 pts, alta/1 h = 150 pts.

**Seed:** 152 tarefas (lista em `docs/ADVBOX-ESPECIFICACAO-COMPLETA.md` §3.8) + 3 sistêmicas
(`Intimações Judiciais`, `Pauta de audiências`, `RECADO/RESPOSTAS`) com `is_system = true`.
Pontuações conhecidas do levantamento são aplicadas; as demais saem da matriz.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/task-types?step_id=&status=&q=` | autenticado |
| POST/PUT/DELETE | `/api/v1/task-types[/{id}]` | **GESTOR** |
| POST | `/api/v1/task-types/suggest-reward` | GESTOR — `{complexity, duration}` → `{reward}` |
| POST | `/api/v1/task-types/transfer` | GESTOR |

## 6. Front-end

**Reutiliza:** `DataTable`, `FilterBar`, `FormModal`, `TransferBeforeDeleteDialog`
**Cria:** `TaskTypeForm` com **calculadora ao vivo** — escolher complexidade e duração atualiza
a sugestão de pontos, que continua editável
**Rota:** `/settings/task-types`

Colunas: Tarefa · Pontuação · Última atribuição · Fase · Cadastro

## 7. Regras de negócio

1. **Só GESTOR** cria, edita ou inativa tipo de tarefa. Administrador e Colaborador só leem.
2. Sugestão de pontos vem da matriz, mas o campo é editável — vence o valor informado.
3. `step_id` nulo = tarefa disponível em todas as fases.
4. Tarefa sistêmica (`is_system`) não pode ser excluída nem renomeada; só a pontuação muda.
5. Excluir tipo em uso exige transferência.
6. Inativar preserva o histórico e a pontuação já creditada.
7. Nome único por tenant, sem acento na comparação.
8. `reward` ≥ 0. Zero é válido (tarefa que não pontua).
9. "Última atribuição" é derivada, não armazenada.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| unit | **matriz completa: 25 combinações** | ~0,3 s |
| unit | ancoragem: simples/15min=8, alta/1h=150 | ~0,1 s |
| integração | CRUD | ~0,4 s |
| integração | Administrador → 403 na escrita | ~0,2 s |
| integração | excluir sistêmica → 403 | ~0,2 s |
| integração | renomear sistêmica → 403 | ~0,2 s |
| integração | alterar pontuação de sistêmica é permitido | ~0,2 s |
| integração | excluir em uso → 409; com transferência funciona | ~0,4 s |
| integração | reward negativo → 422 | ~0,2 s |
| integração | RLS entre tenants | ~0,3 s |
| unit | seed cria 152 + 3 sistêmicas | ~0,2 s |
| frontend | calculadora atualiza ao trocar os selects | ~0,4 s |
| frontend | valor editado manualmente prevalece | ~0,3 s |

**Total:** ~3,4 s

## 9. Descobertas

- **O levantamento titula "152" mas lista 149 nomes únicos.** Seedamos os 149
  documentados — 149 + 3 sistêmicas = 152 linhas por tenant, provável origem do número
  no título da fonte. Nenhum nome foi inventado para "completar" 152. O teste de seed
  do plano ("152 + 3") virou teste de integridade do catálogo (149 + 3).
- **O levantamento não tem complexidade/duração por tarefa** — só nomes e 19 pontuações
  observadas. "As demais saem da matriz" (§4) não era executável sem inventar
  classificação: as 130 sem pontuação observada nascem com `reward = 0` (regra 8: zero
  é válido) e complexity/duration NULL; o gestor classifica ao usar.
- **As 19 pontuações observadas não pertencem à matriz** (80, 100, 200… não são valores
  da grade 5×5) — evidência de que `reward` é valor livre e a matriz só sugere. O
  mapeamento nome→pontos exigiu normalização: 4 dos 19 nomes divergem da grafia do
  catálogo ("ATENDIMENTO AO CLIENTE - EXTERNO" × "…EXTERNO", "DEVOLUÇÃO DE
  DOCUMENTOS/PROCESSO", "FAZER RELATÓRIO DE COMISSÃO MENSAL DO PARCEIRO", "GERENCIAR
  ANÚNCIOS DO ESCRITÓRIO SEMANAL") e 1 é typo da fonte preservado de propósito
  ("DIGILITALIZAÇÃO" — grafia real do ADVBOX).
- **"Em uso → 409" não é testável em integração até a 032** (não existe `tasks`). A
  guarda ficou armada em `TaskTypeService.delete`/`transfer` com `usage_count`/
  `reassign` no repositório (hoje sempre 0); o caminho do 409 está coberto por teste
  unitário com repositório fake (LSP), e a 032 só pluga a contagem real — sem mudar
  contrato. Mesmo padrão documentado das taxonomias da 014/015 (dívida #13).
- **Ruff/black no `make lint`:** enums em migration com `create_table` emitem CREATE
  TYPE sozinhos (reincidência da lição da 023 — a tentativa de criar explícito deixou
  tipo órfão no primeiro run e exigiu DROP + re-run).
- **Wall-clock:** 113 s (teto 120 s) — a suíte backend oscilou 74→108 s nesta rodada
  com todos os testes ~1,0–1,4 s (normal 0,3–0,5 s): contenção do host Docker
  compartilhado, não regressão de código (o perfil mostra o aumento espalhado, sem
  outlier ligado à 031). Observar a tendência na 040.

## 10. Definição de pronto

- [x] Spec escrita seguindo o template (já existia do ciclo de planejamento)
- [x] Escopo implementado: `task_types` + enums + matriz 5×5 + seed (149+3) + CRUD com
      RBAC GESTOR + suggest-reward + transfer + tela /settings/task-types
- [x] Testes do plano escritos e verdes (26 unit de matriz/ancoragem, 2 unit catálogo,
      1 unit guarda regra 5, 6 integração, 2 frontend) — **matriz com 25 casos testados** ✅
- [x] `make lint` verde
- [x] `make test` verde em 113 s (< 120 s)
- [x] `test-timing.json` atualizado
- [x] ROADMAP marcado ✅
- [x] Commit `feat(031): catálogo de tarefas e Taskscore`

## 10. Definição de pronto

Checklist padrão · Matriz com 25 casos testados · Commit `feat(031): catálogo de tarefas e Taskscore`
