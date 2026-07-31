# 036 — Caixa de entrada

**Fase:** 3 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 033, 007 · **Status:** ⬜ pendente

---

## 1. Objetivo

A tela em que o advogado abre o sistema e trabalha o dia inteiro. Tarefas agrupadas em seções
priorizadas, com ações em massa e ordem configurável.

## 2. Escopo

- 6 seções: Prazo fatal · Intimações · Não lidas · Urgentes · Importantes · Todas as demais
- Ordem das seções configurável por usuário
- Ações em massa: concluir, marcar lida, favoritar, reatribuir
- Contadores por seção com colapso
- Configuração em `Configurações > Caixa de entrada`

## 3. Fora de escopo

- Painel de Taskscore → 039 · Agenda → 037

## 4. Modelo de dados

```sql
CREATE TABLE inbox_preferences (
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  section_order TEXT[] NOT NULL DEFAULT
    ARRAY['deadline','publications','unread','urgent','important','others'],
  collapsed_sections TEXT[] NOT NULL DEFAULT '{}',
  page_size SMALLINT NOT NULL DEFAULT 100,
  PRIMARY KEY (user_id)
);
```
RLS ligado. Migration `036_inbox_preferences.py`.

## 5. Contratos de API

| Método | Rota |
|---|---|
| GET | `/api/v1/inbox?section=&cursor=&limit=` |
| GET | `/api/v1/inbox/counts` |
| GET/PUT | `/api/v1/inbox/preferences` |
| POST | `/api/v1/posts/bulk/complete` · `/bulk/read` · `/bulk/star` · `/bulk/reassign` |

## 6. Front-end

**Reutiliza:** `DataTable`, `EmptyState`, `ConfirmDialog`
**Cria:** `InboxPage`, `InboxSection` (colapsável, com contador), `BulkActionBar`,
`InboxSettingsForm` (reordenação por drag & drop)
**Rota:** `/home` (aba Lista)

Colunas: ☑ · ★ · ! · ● · Tarefa · Partes · Data compromisso · Prazo fatal · Responsáveis

## 7. Regras de negócio

1. Cada tarefa aparece em **uma seção só** — a primeira em que se encaixa, na ordem configurada.
2. Definição das seções:
   - `deadline`: `deadline_date` ≤ hoje + 7 dias, não concluída
   - `publications`: tipo sistêmico "Intimações Judiciais"
   - `unread`: `is_read = false`
   - `urgent` / `important`: pela flag
   - `others`: o resto
3. Só tarefas em que o usuário é responsável. Tarefa privada de terceiro nunca aparece.
4. Tarefa `is_future` fica oculta até `scheduled_date`.
5. Concluída sai da caixa de entrada imediatamente.
6. Ações em massa são transacionais: ou todas, ou nenhuma. Falha parcial → 409 com os ids problemáticos.
7. Reatribuir em massa exige ADMINISTRADOR.
8. Contadores vêm em uma query única para as 6 seções, não seis queries.
9. Reordenação de seções persiste por usuário.
10. Paginação keyset por seção, independente entre elas.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | tarefa aparece em uma seção só | ~0,4 s |
| integração | ordem configurada muda a seção de destino | ~0,4 s |
| integração | privada de terceiro não aparece | ~0,3 s |
| integração | futura oculta até a data | ~0,3 s |
| integração | concluída sai da caixa | ~0,3 s |
| integração | ação em massa é transacional | ~0,4 s |
| integração | falha parcial → 409 com ids | ~0,3 s |
| integração | reatribuir sem ser ADMIN → 403 | ~0,2 s |
| integração | **contadores em 1 query** | ~0,4 s |
| integração | keyset independente por seção | ~0,4 s |
| frontend | seções colapsam e persistem | ~0,4 s |
| frontend | barra de ação em massa aparece com seleção | ~0,4 s |
| frontend | reordenação por drag & drop | ~0,4 s |
| e2e | **jornada 5/25:** criar tarefa → aparece na inbox → concluir em massa | ~5 s |

**Total:** ~9,6 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Contadores em query única · Commit `feat(036): caixa de entrada`
