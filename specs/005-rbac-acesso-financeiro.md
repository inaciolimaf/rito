# 005 — RBAC e acesso financeiro

**Fase:** 0 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 004 · **Status:** ⬜ pendente

---

## 1. Objetivo

Autorização em duas dimensões **independentes**, como no ADVBOX: o perfil define o que a pessoa
faz no sistema; o acesso financeiro define, separadamente, o que ela enxerga de dinheiro.

## 2. Escopo

- Enum `UserRole`: `GESTOR`, `ADMINISTRADOR`, `COLABORADOR`
- Enum `FinancialAccess`: `NONE`, `READ_ONLY`, `FULL`
- Colunas em `users`
- Dependencies `require_role(min_role)` e `require_financial(level)`
- Matriz de permissões declarativa em `app/core/permissions.py`
- `GET /auth/me` passa a devolver perfil e capacidades

## 3. Fora de escopo

- UI de gestão de permissões → 012
- Permissão por registro (privacidade de tarefa) → 033

## 4. Modelo de dados

```sql
CREATE TYPE user_role AS ENUM ('GESTOR','ADMINISTRADOR','COLABORADOR');
CREATE TYPE financial_access AS ENUM ('NONE','READ_ONLY','FULL');

ALTER TABLE users
  ADD COLUMN role user_role NOT NULL DEFAULT 'COLABORADOR',
  ADD COLUMN financial_access financial_access NOT NULL DEFAULT 'NONE';
```

Migration: `alembic/versions/005_rbac.py`

## 5. Contratos de API

`GET /api/v1/auth/me` passa a incluir:

```json
{ "role": "GESTOR", "financial_access": "FULL",
  "capabilities": ["settings.manage","tasks.catalog.edit","financial.write", "..."] }
```

Negação retorna `403` em problem+json, com `detail` dizendo qual permissão faltou.

## 6. Front-end

Nenhum ainda, mas `capabilities` já é o contrato que a UI vai consumir em 006+ para esconder
ações. **Esconder na UI não substitui checar no backend.**

## 7. Regras de negócio

1. Hierarquia: `GESTOR` > `ADMINISTRADOR` > `COLABORADOR`. `require_role(ADMINISTRADOR)` aceita Gestor.
2. Acesso financeiro é **ortogonal** ao perfil — existe Colaborador com `FULL` e Gestor com `NONE`.
3. `NONE` → nem lê rota financeira. `READ_ONLY` → só GET. `FULL` → escreve.
4. Só `GESTOR` edita o catálogo de tarefas, metas, taxonomias e configurações estruturais.
5. Toda rota declara sua exigência explicitamente. Rota sem declaração **falha no teste de cobertura de permissão**.
6. Negação é `403`, nunca `404` — a existência do recurso não é segredo aqui.
7. `capabilities` é derivado da matriz, nunca persistido.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| integração | Colaborador → 403 em rota de Gestor | `tests/integration/test_rbac.py` | ~0,3 s |
| integração | Gestor acessa rota de Administrador | idem | ~0,2 s |
| integração | `NONE` → 403 em GET financeiro | `tests/integration/test_financial_access.py` | ~0,3 s |
| integração | `READ_ONLY` → GET ok, POST 403 | idem | ~0,4 s |
| integração | `FULL` → escreve | idem | ~0,3 s |
| integração | Colaborador com `FULL` acessa financeiro | idem | ~0,3 s |
| integração | Gestor com `NONE` é barrado no financeiro | idem | ~0,3 s |
| **meta** | **toda rota registrada declara permissão** | `tests/integration/test_permission_coverage.py` | ~0,5 s |
| unit | matriz de capabilities por perfil | `tests/unit/test_permissions.py` | ~0,2 s |

**Total estimado:** ~2,8 s

> O teste de cobertura de permissão varre `app.routes` e falha se alguma rota de `/api/v1`
> (fora de `/auth` e `/health`) não declarar exigência. Isso impede rota nova nascer aberta —
> vale para as 95 specs seguintes.

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

- [ ] Duas dimensões independentes e testadas
- [ ] Teste de cobertura de permissão ativo
- [ ] `capabilities` no `/auth/me`
- [ ] Commit `feat(005): RBAC e acesso financeiro`
