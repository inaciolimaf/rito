# 036 — Caixa de entrada

**Fase:** 3 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 033, 007 · **Status:** ✅ concluída (2026-08-03)

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

- **A ordem default torna "Não lidas" guarda-chuva:** `unread` precede `urgent` e
  `important` na ordem padrão (regra 1 + regra 2 literais), então a seção Urgentes
  mostra só urgentes JÁ LIDAS. É o comportamento especificado — quem quiser urgente
  sempre no topo reordena em Configurações (regra 9). O teste de contadores documenta
  isso criando urgentes/importantes lidas.
- **Seção é CASE WHEN na ordem configurada, em SQL:** a mesma expressão serve à
  listagem (WHERE section = X com keyset) e aos contadores (GROUP BY — regra 8, uma
  query). A subquery-base carrega o escopo das regras 3–5 (responsável, não concluída
  por ele, futura só depois da data); privada de terceiro nem chega (o usuário não é
  responsável por ela).
- **`/posts/bulk/*` precisa registrar ANTES de `/posts/{post_id}/*`:** o match por
  ordem de registro do FastAPI mandava "bulk" para o parâmetro uuid → 422. O
  inbox_router entrou antes do posts_router no main.py.
- **Bulk opera na linha do PRÓPRIO usuário** (complete/read/star — a caixa só mostra
  tarefas em que ele é responsável); falha em qualquer id → 409 com `failed_ids` como
  membro de extensão do problem+json (mesmo padrão do existing_id da 032) e rollback
  do lote inteiro (regra 6). Reassign troca TODOS os responsáveis e exige
  ADMINISTRADOR+ (regra 7). Conclusão em massa dispara a recorrência da 034 quando a
  tarefa fecha como um todo.
- **inbox_preferences:** PK surrogate + UNIQUE(user_id) (padrão Base do projeto — o
  efeito da PK (user_id) da spec é o mesmo). Preferência materializa no primeiro GET.
- **Três correções de ambiente e2e no caminho:**
  1. O banco de DEV (`rito`, usado pelo webServer do Playwright) estava 3 migrations
     atrás — jornada 5 quebrava com `relation "notifications" does not exist`.
     Migrado; o run-tests.sh só migra o rito_test, o dev é responsabilidade do `make
     migrate` (registrado para a 040 avaliar migrar o dev no webServer do e2e).
  2. O 6º login da suíte e2e (5 jornadas × UI + setups de API, mesmo e-mail/IP em
     <60s) tomava 429 — o limite de login virou configurável por env
     (`LOGIN_RATE_LIMIT`, default 5 em produção, 100 no webServer do Playwright).
  3. Causa raiz das chaves `login_attempts:*` SEM TTL (flake da 034/035): processo
     que morre entre o `incr` e o `expire`. `check_and_increment` agora rearma o TTL
     quando encontra chave sem expiração (ttl<0).
- **Wall-clock: o vitest é quem absorve a fila.** Medido neste host (4 cores): pytest
  isolado é I/O-bound (57 s, ~1,1 core) e vitest CPU-bound (42 s, ~1,9 core); com 2
  threads de vitest o backend esticava para 130-147 s. `run-tests.sh` fixou
  `VITEST_MAX_WORKERS=1` (backend concorrente ~85 s, wall ~105 s na janela boa) —
  a suíte mais barata absorve a contenção. Host compartilhado segue oscilando
  (carga externa 8+), então retries em janela calma continuam necessários.

## 10. Definição de pronto

- [x] Migration `036_inbox_preferences` aplicada (RLS + UNIQUE por usuário)
- [x] 6 seções com uma linha por tarefa na ordem configurada (regras 1–2)
- [x] Escopo: só responsável, privada de terceiro fora, futura oculta, concluída sai
  (regras 3–5) — integração
- [x] Contadores em query única (regra 8), preferências persistidas por usuário
  (regra 9), keyset independente por seção (regra 10) — integração
- [x] Bulk complete/read/star/reassign transacional com 409 + failed_ids (regra 6) e
  reassign 403 para COLABORADOR (regra 7) — integração
- [x] `InboxPage` em /home com `InboxSection` colapsável, `BulkActionBar` e
  `InboxSettingsForm` com drag & drop (3 testes frontend)
- [x] Jornada e2e 5/25: criar tarefa → aparece na caixa → concluir em massa
- [x] Isolamento de tenant em inbox_preferences (RLS direto no banco)
- [x] `make lint` verde · `make test` verde em **116 s** (orçamento 120 s)
- [x] Commit `feat(036): caixa de entrada`
