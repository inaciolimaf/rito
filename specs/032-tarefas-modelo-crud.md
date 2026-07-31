# 032 — Tarefas: modelo e CRUD

**Fase:** 3 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 031, 022 · **Status:** ⬜ pendente

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

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Commit `feat(032): tarefas — modelo e CRUD`
