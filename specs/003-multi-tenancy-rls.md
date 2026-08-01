# 003 — Multi-tenancy com Row Level Security

**Fase:** 0 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 002 · **Status:** ✅ concluída

---

## 1. Objetivo

Isolamento de dados entre escritórios garantido **pelo banco**, não pela aplicação. A partir
daqui, toda tabela de domínio nasce com `tenant_id` e RLS ligado. Esta é a spec mais cara de
retrofitar — por isso é a terceira.

## 2. Escopo

- Tabela `tenants`
- Convenção `tenant_id UUID NOT NULL` + política RLS para tabelas de domínio
- `app/core/rls.py` — `SET LOCAL app.tenant_id` no início de cada transação
- Middleware/dependency que resolve o tenant (por enquanto via header `X-Tenant-Id`; em 004 passa a vir do JWT)
- `BaseRepository` genérico: CRUD, filtros, paginação keyset, ordenação
- `TenantMixin` para os modelos
- Helper de migration `enable_rls(table_name)` reutilizável por todas as specs seguintes
- Role de banco `rito_app` **sem** `BYPASSRLS`

## 3. Fora de escopo

- Autenticação e resolução de tenant pelo token → 004
- RBAC → 005

## 4. Modelo de dados

```sql
CREATE TABLE tenants (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  slug        TEXT NOT NULL UNIQUE,
  name        TEXT NOT NULL,
  is_active   BOOLEAN NOT NULL DEFAULT true,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- padrão aplicado a toda tabela de domínio:
ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;
ALTER TABLE <t> FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON <t>
  USING      (tenant_id = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid);
CREATE INDEX ix_<t>_tenant ON <t> (tenant_id);
```

Uma tabela de exemplo (`tenant_probe`) é criada só para os testes de isolamento.

Migration: `alembic/versions/003_tenants_and_rls.py`

## 5. Contratos de API

Nenhum endpoint público. O contrato aqui é interno: toda sessão obtida por `get_session`
já vem com `app.tenant_id` setado.

## 6. Front-end

Nenhum.

## 7. Regras de negócio

1. `SET LOCAL app.tenant_id` roda dentro da transação — nunca vaza entre conexões do pool.
2. Query sem tenant no contexto retorna **zero linhas**, nunca todas. `current_setting(..., true)` devolve NULL e a política nega.
3. `INSERT` com `tenant_id` diferente do contexto é rejeitado pelo `WITH CHECK`.
4. A aplicação **não** filtra `tenant_id` no `WHERE`. Quem garante é o RLS.
5. `FORCE ROW LEVEL SECURITY` ligado — nem o dono da tabela escapa.
6. A role da aplicação não tem `BYPASSRLS`.
7. `BaseRepository` nunca expõe método que aceite `tenant_id` do chamador.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| RLS | tenant A não lê linha de tenant B | `tests/integration/test_rls.py` | ~0,4 s |
| RLS | `INSERT` com tenant alheio é rejeitado | idem | ~0,3 s |
| RLS | `UPDATE`/`DELETE` cruzando tenant não afeta linhas | idem | ~0,4 s |
| RLS | sem contexto → 0 linhas (não todas) | idem | ~0,3 s |
| RLS | contexto não vaza entre requests no mesmo pool | idem | ~0,5 s |
| unit | `BaseRepository` pagina por keyset | `tests/unit/test_base_repository.py` | ~0,2 s |
| unit | helper `enable_rls` gera o SQL esperado | `tests/unit/test_rls_helper.py` | ~0,1 s |

**Total estimado:** ~2,2 s

## 9. Descobertas

- **Role de aplicação de verdade, não decorativa.** `POSTGRES_USER=rito` (docker-compose) vira
  superusuário do cluster no imagem oficial do Postgres — superusuário **sempre** ignora RLS,
  mesmo com `FORCE ROW LEVEL SECURITY`. Se os testes continuassem conectando como `rito`, os 5
  testes de isolamento passariam ou falhariam por acidente, sem nunca exercitar a política de
  fato. Por isso a migration cria a role `rito_app` (sem `BYPASSRLS`, sem `SUPERUSER`) e o
  runtime/testes passaram a usar duas connection strings: `DATABASE_URL` (role `rito_app`, RLS
  vale) e `MIGRATIONS_DATABASE_URL` (superusuário `rito`, só para `alembic upgrade`, que precisa
  criar tabela/role/policy). `.env.example` documenta as duas, com os pares `TEST_*` equivalentes.
- `CREATE ROLE` é operação de **cluster**, não de banco — `rito` e `rito_test` são dois bancos
  no mesmo cluster Postgres. A migration usa um bloco `DO $$ ... IF NOT EXISTS ... $$` para criar
  a role de forma idempotente (ela só é criada da primeira vez, em qualquer um dos dois bancos
  que rodar a migration primeiro); os `GRANT`s, esses sim por banco, rodam sempre.
- `SET LOCAL app.tenant_id = ...` não aceita bind parameter no asyncpg (comando `SET` não passa
  pelo protocolo estendido do Postgres). O helper `set_tenant_context` usa
  `SELECT set_config('app.tenant_id', :tenant_id, true)` em vez disso — `set_config` é uma
  função normal, aceita parâmetro ligado, e `is_local=true` tem o mesmo efeito transacional do
  `SET LOCAL`.
- **GUC customizado "resetado" não é NULL depois do primeiro uso na conexão.** Descoberto no
  teste de "sem contexto → 0 linhas": a primeira vez que uma conexão nunca tocou
  `current_setting('app.tenant_id', true)` ele devolve `NULL`; mas depois que a MESMA conexão
  física já rodou `set_config(...)` uma vez (mesmo com `is_local=true`, mesmo já tendo
  commitado), o Postgres cria um placeholder para o GUC cujo valor "resetado" passa a ser `''`
  (string vazia) para o resto da vida daquela conexão — e `''::uuid` levanta erro em vez de
  devolver `NULL`. Isso é seguro nos dois formatos (nunca vaza linha), só muda o sintoma (0
  linhas vs. exceção). O teste
  `test_query_without_tenant_context_returns_zero_rows` aceita ambos; comentário no próprio
  teste explica o porquê.
- **Corrida entre workers do `pytest -n auto`.** A tabela de exemplo `tenant_probe` (só para os
  5 testes de RLS) precisou de um nome único por worker do xdist
  (`tenant_probe_{worker_id}`, via a fixture nativa `worker_id` do `pytest-xdist`) — sem isso,
  workers concorrentes criando/derrubando a mesma tabela colidiam de forma não-determinística
  (`4 workers`, falhas diferentes a cada rodada). Rodei a suíte 4x seguidas com `-n auto` para
  confirmar que a corrida sumiu.
- `get_tenant_id`/`get_session` (dependências FastAPI em `app/core/deps.py`) ainda não têm
  nenhum router de domínio para exercitá-los ponta a ponta — não há teste HTTP direto deles
  nesta spec porque o plano de testes não pedia (só os 5 de RLS + 2 unit). Cobertura real via
  HTTP chega com o primeiro CRUD de domínio (011+). `health.py` continua usando
  `request.app.state.session_factory` direto, sem tenant — decisão deliberada, health check não
  toca tabela nenhuma sujeita a RLS.
- `downgrade()` da migration não tenta apagar a role `rito_app`: ela é compartilhada entre
  `rito` e `rito_test` no mesmo cluster, e `DROP ROLE` falha com "objects depend on it" se
  houver qualquer grant pendente em QUALQUER banco do cluster, não só o que está rodando o
  downgrade. O downgrade só desfaz os grants daquele banco e derruba a tabela `tenants` — a
  role, se for realmente preciso removê-la, é uma ação manual fora de migration.
- Removi `get_session_from_factory` (`app/core/db.py`), que sobrou da 002 sem nenhum uso —
  substituído por `create_engine_from_url` (usado pelos testes para instanciar engines com
  `MIGRATIONS_DATABASE_URL`/`DATABASE_URL` explícitas, fora do `get_settings()` cacheado).
  `BaseRepository`/`build_keyset_query` usam a nova sintaxe de generics do Python 3.12
  (`class BaseRepository[ModelT: Base]`) em vez de `TypeVar`+`Generic` — `ruff` (regra `UP046`/
  `UP047`) sinalizou a forma antiga como código a modernizar.

## 10. Definição de pronto

- [x] Os 5 testes de RLS passam (rodado 4x com `-n auto` para validar contra corrida entre
      workers)
- [x] Helper `enable_rls`/`enable_rls_statements` pronto para as specs seguintes
- [x] `BaseRepository` — interface bate com o que o `CLAUDE.md` já descreve (CRUD + paginação
      keyset); nada a atualizar lá
- [x] Commit `feat(003): multi-tenancy com RLS`
