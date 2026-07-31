# 033 — Tarefas: flags e conclusão

**Fase:** 3 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 032 · **Status:** ⬜ pendente

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

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Privacidade testada contra GESTOR · Commit `feat(033): tarefas — flags e conclusão`
