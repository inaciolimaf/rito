# 005 — RBAC e acesso financeiro

**Fase:** 0 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 004 · **Status:** ✅ concluída

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

- **`UserRole`/`FinancialAccess` moraram em `app/domain/users/models.py`, não em
  `app/core/permissions.py`.** A spec pede a matriz declarativa em `core/permissions.py`, mas
  colocar os enums lá criaria um ciclo de import real:
  `users.models` → `permissions` (pelos enums) → `auth.deps` (por `get_current_user`) →
  `users.models` (por `User`) — fechando o círculo. Como os enums são, na prática, tipos de
  coluna do `User`, ficaram co-localizados com o modelo; `core/permissions.py` importa os dois
  de lá (`get_current_user` de `app.domain.auth.deps`, os enums de `app.domain.users.models`) e
  contém só a matriz/hierarquia/`require_role`/`require_financial` — que é o que a spec
  realmente quer dizer com "matriz declarativa". `core` depender de `domain` aqui é uma exceção
  deliberada (autorização por natureza cruza a fronteira entre "infra" e "quem é o usuário"),
  não um desvio de camada por descuido.
- **`require_role`/`require_financial` usam o MESMO mecanismo de ordinal** (`_ROLE_ORDER`/
  `_FINANCIAL_ORDER`, um dicionário perfil→inteiro) para as duas dimensões. Isso faz a regra 3
  (`NONE` bloqueia tudo, `READ_ONLY` só GET, `FULL` escreve) cair de graça: uma rota GET
  declara `require_financial(READ_ONLY)` (READ_ONLY e FULL passam, NONE não), uma rota de
  escrita declara `require_financial(FULL)` (só FULL passa) — nenhuma lógica especial por
  método HTTP foi necessária, só a rota certa escolhendo o mínimo certo.
- **Sem rota de domínio protegida ainda** (só a 011+ vai criar a primeira). Os testes de
  RBAC/financeiro precisaram de um app FastAPI descartável com 4 rotas de exemplo
  (`rbac_client` em `tests/integration/conftest.py`, mesmo padrão do `test_errors.py` da 002),
  já que `require_role`/`require_financial` só existem de verdade quando ligados a uma rota
  real. `test_permission_coverage.py` tem duas partes: uma rodando contra o app REAL (hoje
  passa vazio, porque só `/auth` existe) e outra provando que o scanner realmente pega uma
  rota ruim (contra um app sintético) — sem isso o primeiro teste seria só uma verdade vazia.
- `enum.StrEnum` em vez de `class X(str, enum.Enum)` — `ruff` (regra `UP042`) sinalizou a
  segunda forma como redundante em Python 3.12+; ambas se comportam igual para
  SQLAlchemy/Pydantic (instâncias continuam sendo `str`).
- `make_user` (fixture da 004) ganhou `role`/`financial_access` como parâmetros opcionais
  (default `COLABORADOR`/`NONE`, iguais ao banco) — reusado por todos os testes novos sem
  duplicar a lógica de seed de tenant+usuário.
- Nenhuma UI, permissão por registro ou tela de gestão de permissões foi tocada — confirma o
  "fora de escopo" (012, 033).

## 10. Definição de pronto

- [x] Duas dimensões independentes e testadas (perfil × financeiro — Colaborador com `FULL` e
      Gestor com `NONE` cobertos explicitamente)
- [x] Teste de cobertura de permissão ativo (`test_permission_coverage.py`, rodando contra o
      app real E provando que detecta uma rota sem declaração)
- [x] `capabilities` no `/auth/me` (derivado da matriz, nunca persistido — regra 7)
- [x] Commit `feat(005): RBAC e acesso financeiro`
