# 003 — Multi-tenancy com Row Level Security

**Fase:** 0 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 002 · **Status:** ⬜ pendente

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

*(preencher)*

## 10. Definição de pronto

- [ ] Os 5 testes de RLS passam
- [ ] Helper `enable_rls` pronto para as specs seguintes
- [ ] `BaseRepository` documentado no `CLAUDE.md` se a interface mudar
- [ ] Commit `feat(003): multi-tenancy com RLS`
