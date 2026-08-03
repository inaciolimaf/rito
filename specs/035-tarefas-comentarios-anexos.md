# 035 — Tarefas: comentários, menções e anexos

**Fase:** 3 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 032 · **Status:** ✅ concluída (2026-08-03)

---

## 1. Objetivo

Transformar a tarefa no lugar onde a conversa sobre o caso acontece: thread de comentários,
`@menções` que notificam e anexos.

## 2. Escopo

- Tabela `post_comments` com thread
- `@menções` com autocomplete e notificação
- Anexos em comentário e na tarefa
- Registro de leitura por usuário

## 3. Fora de escopo

- Storage definitivo → 063 (aqui, interface `FileStorage` com implementação local)
- Canais de notificação (e-mail/SMS/WhatsApp) → 069 (aqui só notificação in-app)

## 4. Modelo de dados

```sql
CREATE TABLE post_comments (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  post_id UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  author_id UUID NOT NULL REFERENCES users(id),
  body TEXT NOT NULL,
  mentioned_user_ids UUID[] NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ
);
CREATE INDEX ix_comments_post ON post_comments (post_id, created_at);

CREATE TABLE attachments (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  storage_key TEXT NOT NULL,
  filename TEXT NOT NULL,
  content_type TEXT NOT NULL,
  size_bytes BIGINT NOT NULL,
  attached_to_type TEXT NOT NULL,   -- 'post' | 'comment' | 'customer' | 'transaction'
  attached_to_id UUID NOT NULL,
  uploaded_by UUID NOT NULL REFERENCES users(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_attachments_target ON attachments (tenant_id, attached_to_type, attached_to_id);

CREATE TABLE notifications (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  user_id UUID NOT NULL REFERENCES users(id),
  kind TEXT NOT NULL,               -- 'mention' | 'assignment' | 'deadline' | ...
  title TEXT NOT NULL,
  body TEXT,
  link TEXT,
  read_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_notifications_unread ON notifications (tenant_id, user_id, created_at DESC)
  WHERE read_at IS NULL;
```
RLS nas três. Migration `035_comments_attachments_notifications.py`.

`attachments` e `notifications` são genéricas — reutilizadas por contatos, financeiro e IA.

## 5. Contratos de API

| Método | Rota |
|---|---|
| GET/POST | `/api/v1/posts/{id}/comments` |
| PUT/DELETE | `/api/v1/comments/{cid}` |
| POST | `/api/v1/attachments` (multipart) |
| GET | `/api/v1/attachments/{id}/download` |
| DELETE | `/api/v1/attachments/{id}` |
| GET | `/api/v1/notifications?unread=true&cursor=` |
| POST | `/api/v1/notifications/{id}/read` · `/read-all` |
| GET | `/api/v1/users/mentionable?q=` |

## 6. Front-end

**Reutiliza:** `ConfirmDialog`, `EmptyState`
**Cria:** `CommentThread`, `CommentEditor` (autocomplete de `@`), `AttachmentList`,
`FileDropzone`, `NotificationPanel`
**Rota:** dentro do detalhe da tarefa e no `NotificationBell` do header

## 7. Regras de negócio

1. `@menção` é resolvida na gravação e persistida em `mentioned_user_ids` — renomear o usuário depois não quebra o link.
2. Menção só notifica quem tem acesso à tarefa; menção a quem não tem é ignorada silenciosamente.
3. Autor edita o próprio comentário em até 15 min; depois só ADMINISTRADOR.
4. Exclusão é soft; a UI mostra "comentário removido" preservando a thread.
5. Anexo: máx. 50 MB, tipos permitidos por allowlist; executáveis bloqueados.
6. Download por URL assinada com validade de 5 min.
7. Anexo em tarefa privada segue a mesma restrição de visibilidade.
8. Notificação de menção é in-app; o roteamento por canal vem em 069.
9. Excluir comentário remove os anexos dele.
10. Thread ordenada por criação crescente, paginada a partir de 50.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | criar comentário e listar thread | ~0,4 s |
| integração | menção gera notificação | ~0,3 s |
| integração | menção a quem não tem acesso é ignorada | ~0,3 s |
| integração | menção sobrevive à renomeação do usuário | ~0,3 s |
| integração | edição após 15 min → 403 | ~0,3 s |
| integração | exclusão é soft e preserva a thread | ~0,3 s |
| integração | upload acima de 50 MB → 422 | ~0,3 s |
| integração | tipo bloqueado → 422 | ~0,2 s |
| integração | URL de download expira | ~0,3 s |
| integração | anexo de tarefa privada respeita visibilidade | ~0,3 s |
| integração | RLS nas três tabelas | ~0,4 s |
| frontend | autocomplete de `@` | ~0,5 s |
| frontend | dropzone valida tipo e tamanho | ~0,4 s |

**Total:** ~4,3 s

## 9. Descobertas

- **Menção é casamento de nome, não token tipado.** O editor insere `@Nome Completo` em
  texto livre; o backend casa os nomes dos usuários ativos contra o corpo (normalizado,
  sem acento/caixa; nomes mais longos primeiro; boundary não-alfabético) e persiste os
  ids (regra 1). Dois usuários homônimos são mencionados juntos — limitação aceita do
  texto livre. Edição re-resolve e notifica só quem ENTROU na lista.
- **Acesso à tarefa é a régua de tudo.** Comentar, anexar, baixar e listar anexos
  verificam a mesma regra 8 da 033 (privada = só criador/responsáveis, 404 não 403).
  A regra saiu de `posts/service.py` para `posts/visibility.py` (regra dos 3 usos:
  posts, attachments, comments).
- **URL assinada precisou de `signature_version="s3v4"` no boto3:** com endpoint
  customizado (MinIO) o cliente caía na s3v2 legada (`Expires=<epoch>`), quebrando a
  regra 6 verificável. `FileStorage` ganhou `signed_url(key, expires_in_seconds)` e
  `delete(key)`; `public_url` virou atalho da assinada de 7 dias (logo inalterado).
- **Cursor keyset em coluna de data precisa de `datetime`, não string** — comparar
  `timestamptz > character varying` não existe no Postgres. O `BaseRepository` só cobre
  coluna texto; comments/notifications decodificam o cursor para `datetime` e usam
  `tuple_` + `literal()` (mesma lição do mypy no `build_sorted_keyset_query`).
- **`NotificationRepository.create` virou `create_notification`** — a assinatura por
  kwargs conflitava com `BaseRepository.create(instance)` (LSP/mypy override).
- **Delete de storage é best-effort** (`contextlib.suppress`): órfão no bucket é
  preferível a falhar a exclusão da linha por erro de MinIO.
- **Revision id da migration limitado a 32 chars** (`alembic_version.version_num` é
  varchar(32)) — `035_comments_attachments_notifications` estourou em runtime; encurtado
  para `035_comments_attach_notifs`.
- **GET `/attachments?attached_to_type=&attached_to_id=`** entrou além da tabela do §5
  (a listagem dos anexos da tarefa na UI precisava; a thread já traz os de comentário).
- **Causa raiz do estouro intermitente de wall-clock (da 034):** vitest default é
  1 thread/core — 4 threads node a 100% + `pytest -n auto` + playwright/vite/uvicorn
  num host de 4 cores esticava o backend (suíte mais longa) de ~47 s isolado para
  118–130 s. `run-tests.sh` agora capa pytest em `${PYTEST_WORKERS:-2}` e vitest em
  `${VITEST_MAX_WORKERS:-2}`; wall-clock caiu para 89 s estável.

## 10. Definição de pronto

- [x] Migration `035_comments_attach_notifs` aplicada (3 tabelas + RLS + índices)
- [x] Thread de comentários crescente com keyset a partir de 50 (regra 10)
- [x] `@menções` resolvidas na gravação, persistidas como ids, com notificação in-app
  (regras 1, 2, 8) e autocomplete `/users/mentionable`
- [x] Edição do autor em 15 min; depois só ADMINISTRADOR+ (regra 3)
- [x] Exclusão soft com "comentário removido" na thread (regra 4) removendo os anexos
  do comentário (regra 9)
- [x] Upload com allowlist de tipos, executáveis bloqueados e 50 MB (regra 5);
  download por URL assinada de 5 min (regra 6); privada respeitada (regra 7)
- [x] `CommentThread`, `CommentEditor` (@), `AttachmentList`, `FileDropzone`,
  `NotificationPanel` + `NotificationBell` com badge e rota `/posts/:id`
- [x] Isolamento de tenant nas 3 tabelas (API 404 + RLS direto no banco, dois sentidos)
- [x] `make lint` verde · `make test` verde em **89 s** (orçamento 120 s)
- [x] Commit `feat(035): tarefas — comentários, menções e anexos`
