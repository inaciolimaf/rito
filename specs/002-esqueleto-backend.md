# 002 — Esqueleto do backend

**Fase:** 0 · **Tipo:** feature · **Orçamento:** +3 s
**Depende de:** 001 · **Status:** ⬜ pendente

---

## 1. Objetivo

Backend FastAPI que sobe, conecta no Postgres com SQLAlchemy async, aplica migrations do
Alembic e responde a um healthcheck — com tratamento de erro e log estruturado padronizados.

## 2. Escopo

- `app/main.py` com lifespan (pool de conexão)
- `app/core/config.py` — Pydantic Settings lendo `.env`
- `app/core/db.py` — engine async, `async_sessionmaker`, `get_session` como dependency
- `app/core/errors.py` — exception handlers RFC 7807 (`application/problem+json`)
- `app/core/logging.py` — JSON estruturado com `request_id`
- Middleware de `request_id` (aceita `X-Request-Id`, senão gera)
- Alembic configurado para async, com `env.py` lendo `DATABASE_URL`
- `GET /health` (processo vivo) e `GET /health/ready` (Postgres + Redis)

## 3. Fora de escopo

- Tenancy → 003
- Auth → 004
- Qualquer tabela de domínio

## 4. Modelo de dados

Nenhuma tabela de domínio. Migration inicial cria só `alembic_version` e as extensões:

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "unaccent";
```

Migration: `alembic/versions/002_initial_extensions.py`

## 5. Contratos de API

| Método | Rota | Saída |
|---|---|---|
| GET | `/health` | `200 {"status":"ok","version":"..."}` |
| GET | `/health/ready` | `200 {"database":"ok","redis":"ok"}` · `503` se qualquer um falhar |

Formato de erro:
```json
{ "type":"https://rito.app/errors/validation", "title":"Dados inválidos",
  "status":422, "detail":"...", "instance":"/api/v1/...", "errors":[...] }
```

## 6. Front-end

Nenhum.

## 7. Regras de negócio

1. Toda resposta de erro segue RFC 7807 com `content-type: application/problem+json`.
2. Todo log carrega `request_id`; a partir de 003 carrega também `tenant_id`.
3. `/health/ready` retorna 503 se Postgres ou Redis estiverem fora.
4. Exceção não tratada nunca vaza stack trace na resposta — vira 500 genérico + log completo.
5. A sessão do banco é injetada por `Depends`; nenhum módulo cria engine próprio.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| integração | `/health` retorna 200 | `tests/integration/test_health.py` | ~0,2 s |
| integração | `/health/ready` com Redis fora → 503 | idem | ~0,3 s |
| integração | erro de validação → problem+json | `tests/integration/test_errors.py` | ~0,3 s |
| integração | exceção não tratada → 500 sem stack trace | idem | ~0,3 s |
| unit | `request_id` propaga para o log | `tests/unit/test_logging.py` | ~0,1 s |
| unit | Settings falha se faltar variável obrigatória | `tests/unit/test_config.py` | ~0,1 s |

**Total estimado:** ~1,3 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

- [ ] `alembic upgrade head` do zero funciona
- [ ] Healthchecks corretos
- [ ] `make test` verde
- [ ] Commit `feat(002): esqueleto do backend`
