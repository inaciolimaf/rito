# 033 — Tarefas: flags e conclusão

**Fase:** 3 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 032 · **Status:** ✅ concluída

---

## 1. Objetivo

Os atributos que governam como a tarefa aparece e o momento em que ela vira pontuação. A
conclusão é **por responsável**, não da tarefa como um todo — cada pessoa credita seus pontos.

## 2. Escopo

- Flags: importante, urgente, futura, privada, retroativa
- Conclusão individual por responsável, com data e hora
- Crédito de pontuação na conclusão
- Lançamento retroativo
- Reabertura de tarefa concluída

## 3. Fora de escopo

- Recorrência → 034 · Ranking → 039

## 4. Modelo de dados

```sql
ALTER TABLE posts
  ADD COLUMN is_important BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN is_urgent    BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN is_future    BOOLEAN NOT NULL DEFAULT false,  -- oculta até a data
  ADD COLUMN is_private   BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN show_in_schedule BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE post_users
  ADD COLUMN completed_at TIMESTAMPTZ,
  ADD COLUMN points_earned INTEGER,
  ADD COLUMN is_read BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN is_starred BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX ix_post_users_pending ON post_users (tenant_id, user_id)
  WHERE completed_at IS NULL;
CREATE INDEX ix_post_users_completed ON post_users (tenant_id, user_id, completed_at DESC)
  WHERE completed_at IS NOT NULL;
```
Migration `033_post_flags_completion.py`.

## 5. Contratos de API

| Método | Rota |
|---|---|
| POST | `/api/v1/posts/{id}/complete` → `{completed_at?}` (retroativo) |
| POST | `/api/v1/posts/{id}/reopen` |
| POST | `/api/v1/posts/{id}/read` · `/star` |
| PUT | `/api/v1/posts/{id}/flags` |

## 6. Front-end

**Reutiliza:** `ConfirmDialog`
**Cria:** `TaskFlags` (4 checkboxes no formulário), `CompleteTaskButton`,
`RetroactiveDateField`, `PriorityBadge`
**Rota:** dentro do `TaskForm` e da caixa de entrada

## 7. Regras de negócio

1. Conclusão é **por responsável**: cada linha de `post_users` fecha independente.
2. Ao concluir, `points_earned` recebe `reward_snapshot` da tarefa — congelado ali.
3. Tarefa está concluída como um todo quando **todos** os responsáveis concluíram.
4. Retroativa permite `completed_at` no passado; **nunca** no futuro → 422.
5. Retroativa credita os pontos na competência da data informada, não na de hoje.
6. Reabrir zera `completed_at` e `points_earned` daquele responsável.
7. `is_future = true` oculta a tarefa da caixa de entrada até `scheduled_date`.
8. `is_private = true` restringe a visibilidade ao criador e aos responsáveis — nem GESTOR vê. Aparece nas contagens agregadas como "tarefa privada", sem conteúdo.
9. Só quem é responsável conclui a própria linha. ADMINISTRADOR pode concluir pelos outros, e isso fica registrado.
10. Importante e urgente são independentes e combináveis.
11. `is_read` e `is_starred` são por usuário, não da tarefa.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | conclusão individual não fecha para os outros | ~0,4 s |
| integração | todos concluíram → tarefa concluída | ~0,3 s |
| integração | pontos creditados = `reward_snapshot` | ~0,3 s |
| integração | retroativa no futuro → 422 | ~0,2 s |
| integração | retroativa credita na competência certa | ~0,3 s |
| integração | reabrir zera pontos | ~0,3 s |
| integração | privada invisível para não envolvido, inclusive GESTOR | ~0,4 s |
| integração | privada aparece na contagem sem conteúdo | ~0,3 s |
| integração | não responsável não conclui → 403 | ~0,2 s |
| integração | ADMINISTRADOR conclui por outro e fica registrado | ~0,3 s |
| integração | futura oculta até a data | ~0,3 s |
| frontend | badges de prioridade | ~0,3 s |

**Total:** ~3,6 s

## 9. Descobertas

- **`completed_by` não estava no modelo da spec** — mas a regra 9 exige "ADMINISTRADOR
  pode concluir pelos outros, e isso fica registrado". Sem a coluna não há onde
  registrar: adicionada em `post_users` (None = o próprio responsável concluiu).
- **Privacidade é 404, não 403** (regra 8): para o não envolvido, a tarefa privada não
  existe — saber que ela existe já é conteúdo. Na listagem do processo ela aparece
  como presença redigida (`redacted: true`, `task_type_name: "Tarefa privada"`,
  sem responsáveis/datas/comentários) — é a "contagem agregada sem conteúdo" da regra.
  Criador e responsáveis veem tudo.
- **Futura é filtrada no service, não no banco** (regra 7): `is_future` + sem data ou
  data > hoje fica fora da listagem do processo (a caixa de entrada da 036 reusa o
  mesmo predicado). Sem tarefa futura visível para ninguém até o dia — o ponto dela é
  não poluir a agenda antes da hora.
- **Concluir é idempotente**: linha já concluída ignora novo complete (não regrava
  data nem pontos) — um double-click não muda a competência original.
- **read/star são set idempotente com default true** (`POST /read {}` marca;
  `{"value": false}` desmarca) — toggle cego por endpoint separado viraria corrida.
- **Wall-clock 99 s** — a suíte voltou a dois dígitos (backend 95 s): a limpeza do
  rito_test (032) segurou a degradação e a contenção do host arrefeceu nesta rodada.
  A dívida #17 segue aberta (margem era 1 s na 032).
- **Lifespan por sessão NÃO funciona com pytest-asyncio**: a tentativa de subir o app
  uma vez por worker (`loop_scope="session"`) quebrou 151 testes com conexões
  asyncpg presas a loops diferentes (engine criada no loop da sessão, requests no loop
  da função). Revertido e registrado na dívida #17 — a otimização correta desse custo
  não é escopo de fixture.

## 10. Definição de pronto

- [x] Spec escrita seguindo o template (já existia do ciclo de planejamento)
- [x] Escopo implementado: 5 flags, conclusão individual com pontos, retroativa,
      reabertura, read/star por usuário, privacidade e futura com visibilidade testadas
- [x] Testes do plano escritos e verdes (10 integração + 1 frontend — cobrindo os 11
      casos do plano: conclusão individual e total, pontos=snapshot, retroativa 422 e
      competência, reabrir zera, privada invisível p/ GESTOR + presença sem conteúdo,
      não responsável → 403, ADMIN registrado, futura oculta)
- [x] **Privacidade testada contra GESTOR** ✅
- [x] `make lint` verde
- [x] `make test` verde em 99 s (< 120 s)
- [x] `test-timing.json` atualizado
- [x] ROADMAP marcado ✅
- [x] Commit `feat(033): tarefas — flags e conclusão`

## 10. Definição de pronto

Checklist padrão · Privacidade testada contra GESTOR · Commit `feat(033): tarefas — flags e conclusão`
