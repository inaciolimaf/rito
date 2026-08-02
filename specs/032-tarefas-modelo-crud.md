# 032 — Tarefas: modelo e CRUD

**Fase:** 3 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 031, 022 · **Status:** ✅ concluída

---

## 1. Objetivo

A entidade mais usada do sistema. Tarefa, compromisso de agenda, intimação recebida e comentário
são todos `posts` — muda o tipo e os campos preenchidos, não a tabela.

## 2. Escopo

- Tabela `posts` e `post_users` (múltiplos responsáveis)
- CRUD + modal "Criar nova tarefa"
- Vínculo obrigatório a processo e a tipo de tarefa
- Atribuição a usuários ou a time inteiro
- Detecção de duplicata

## 3. Fora de escopo

- Flags e conclusão → 033 · Recorrência → 034 · Comentários e anexos → 035
- Caixa de entrada → 036 · Workflow → 038

## 4. Modelo de dados

```sql
CREATE TABLE posts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  lawsuit_id UUID NOT NULL REFERENCES lawsuits(id) ON DELETE CASCADE,
  task_type_id UUID NOT NULL REFERENCES task_types(id),
  created_by UUID NOT NULL REFERENCES users(id),
  scheduled_date DATE,
  scheduled_time TIME,
  end_date DATE,
  end_time TIME,
  deadline_date DATE,                -- prazo fatal
  all_day BOOLEAN NOT NULL DEFAULT false,
  location TEXT,
  comments TEXT,
  reward_snapshot INTEGER NOT NULL,  -- pontos congelados na criação
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (end_date IS NULL OR scheduled_date IS NULL OR end_date >= scheduled_date),
  CHECK (end_time IS NULL OR end_date IS NOT NULL)
);
CREATE INDEX ix_posts_lawsuit  ON posts (lawsuit_id, scheduled_date DESC);
CREATE INDEX ix_posts_deadline ON posts (tenant_id, deadline_date) WHERE deadline_date IS NOT NULL;
CREATE INDEX ix_posts_type     ON posts (tenant_id, task_type_id);

CREATE TABLE post_users (
  post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  PRIMARY KEY (post_id, user_id)
);
CREATE INDEX ix_post_users_user ON post_users (tenant_id, user_id);
```
RLS nas duas. Migration `032_posts.py`.

`reward_snapshot` congela a pontuação **no momento da criação** — mudar o catálogo depois não
reescreve o histórico de produtividade.

## 5. Contratos de API

| Método | Rota |
|---|---|
| POST | `/api/v1/posts` |
| GET/PUT/DELETE | `/api/v1/posts/{id}` |
| GET | `/api/v1/lawsuits/{id}/posts` |

`POST` aceita `user_ids[]` **ou** `squad_id` (expande para os membros ativos).

## 6. Front-end

**Reutiliza:** `FormModal`, `EntityPicker`, `ConfirmDialog`
**Cria:** `TaskForm`, `AssigneeSelector` (usuários ou time), `TaskTypeSelect` (mostra pontos),
`DeadlineField`
**Rota:** modal global, acessível pelo botão "Adicionar"

## 7. Regras de negócio

1. Obrigatórios: processo, tipo de tarefa, ≥1 responsável.
2. `squad_id` expande para os membros **ativos** no momento da criação; o time não fica vinculado.
3. `reward_snapshot` copia o `reward` do tipo na criação e nunca muda.
4. Duplicata (mesmo processo + tipo + data + mesmo conjunto de responsáveis) → 409 com o id existente.
5. `end_time` exige `end_date` (constraint).
6. `end_date` ≥ `scheduled_date`.
7. Prazo fatal é independente da data de compromisso e pode ser anterior a ela.
8. Excluir processo remove as tarefas (cascade); excluir tarefa não afeta o processo.
9. Responsável precisa ser usuário ativo do tenant.
10. `all_day` ignora os campos de hora.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | CRUD com múltiplos responsáveis | ~0,5 s |
| integração | atribuição por time expande membros ativos | ~0,4 s |
| integração | time com membro inativo não o inclui | ~0,3 s |
| integração | sem responsável → 422 | ~0,2 s |
| integração | duplicata → 409 com id existente | ~0,4 s |
| integração | `end_time` sem `end_date` → 422 | ~0,2 s |
| integração | `end_date` anterior → 422 | ~0,2 s |
| integração | `reward_snapshot` não muda ao editar o catálogo | ~0,4 s |
| integração | excluir processo remove tarefas | ~0,3 s |
| integração | RLS entre tenants | ~0,3 s |
| frontend | `TaskForm` valida e mostra pontos | ~0,4 s |
| frontend | alternar entre usuários e time | ~0,4 s |

**Total:** ~4,0 s

## 9. Descobertas

- **A regra 5 da 031 foi plugada nesta spec** (como registrado nas Descobertas da 031):
  `TaskTypeRepository.usage_count`/`reassign` agora consultam `posts` de verdade, e o
  teste "excluir em uso → 409; com transferência funciona" vive em `test_posts.py`
  (`test_tipo_em_uso_exige_transferencia`) — era o caso do plano da 031 que só a 032
  podia criar.
- **409 da duplicata virou membro de extensão RFC 7807.** O handler de erros só
  conhecia a convenção `{"detail", "errors"}` e stringifyava qualquer outro dict —
  `existing_id` ia perdido. O handler agora promove chaves extras do dict para membros
  de extensão do problem+json (retrocompatível: a convenção de `errors` é inalterada).
- **Duplicata é comparada em Python, não em SQL.** O conjunto de responsáveis por post
  não cabe num predicado simples; o volume de candidatos por (processo, tipo, data) é
  baixo, então o service compara os conjuntos. Detecção só na criação — PUT não
  revalida (mesmo comportamento do ADVBOX, que impede na criação).
- **`updated_at` com `onupdate` server-side expira o atributo no flush** — reincidência
  da MissingGreenlet da 022; o service seta `datetime.now(UTC)` explicitamente no
  update, mesmo remédio de `LawsuitService`.
- **O teste do cascade da regra 8 é hard delete direto no banco** (admin_engine): o
  delete da API de processos é soft desde a 022 — a FK ON DELETE CASCADE é a garantia
  para o hard delete futuro, mesmo padrão das partes (023).
- **Wall-clock à beira do teto (119 s).** A suíte backend saltou de ~74 s (era 029) para
  ~110 s: latência dobrada e espalhada por TODOS os testes aponta contenção do host
  Docker compartilhado, não regressão de código (perfil sem outlier). Contribuinte real
  encontrado e corrigido: `rito_test` acumulava tenants de todas as runs (make_user
  comita) — 9.317 tenants e 1,16 milhão de `task_types` após a seed da 031. O
  `run-tests.sh` agora roda `TRUNCATE tenants CASCADE` antes do pytest (catálogos
  globais ficam). A margem continua fina — registrar na 040.
- **Flake sob carga:** `StateCitySelect.test.tsx` falhou uma vez na suíte concorrente
  (1,9 s no waitFor) e passa isolado em 0,24 s — sintoma da mesma contenção; observar.

## 10. Definição de pronto

- [x] Spec escrita seguindo o template (já existia do ciclo de planejamento)
- [x] Escopo implementado: `posts` + `post_users`, CRUD, vínculo obrigatório, atribuição
      por usuários ou time, detecção de duplicata, modal global "Criar nova tarefa"
- [x] Testes do plano escritos e verdes (10 integração — incluindo o caso "em uso →
      409 + transferência" da 031 — e 2 frontend)
- [x] `make lint` verde
- [x] `make test` verde em 119 s (< 120 s)
- [x] `test-timing.json` atualizado
- [x] ROADMAP marcado ✅
- [x] Commit `feat(032): tarefas — modelo e CRUD`

## 10. Definição de pronto

Checklist padrão · Commit `feat(032): tarefas — modelo e CRUD`
