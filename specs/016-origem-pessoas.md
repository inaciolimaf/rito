# 016 — Origem de pessoas

**Fase:** 1 · **Tipo:** feature · **Orçamento:** +2 s
**Depende de:** 011 · **Status:** ✅ concluída

---

## 1. Objetivo

De onde veio cada contato. Alimenta o gráfico Top Origens (019) e as métricas de conversão
comercial do BI (074).

## 2. Escopo

- Tabela `customer_origins` com 8 origens padrão
- CRUD + transferência em lote
- Tela `Configurações > Origem de pessoas`

## 3. Fora de escopo

- Uso no cadastro de contato → 017
- Métricas de conversão → 074

## 4. Modelo de dados

```sql
CREATE TABLE customer_origins (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  name TEXT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);
```
Migration `016_customer_origins.py`.

**Seed (8):** ANÚNCIO · ESCRITÓRIO · FACEBOOK · GOOGLE · INDICAÇÃO · INSTAGRAM ·
PARTE CONTRÁRIA · SITE DO ESCRITÓRIO

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/customer-origins?status=&q=` | autenticado |
| POST/PUT/DELETE | `/api/v1/customer-origins[/{id}]` | GESTOR |
| POST | `/api/v1/customer-origins/transfer` | GESTOR |

## 6. Front-end

**Reutiliza:** `DataTable`, `FormModal`, `TransferBeforeDeleteDialog`
**Cria:** nada
**Rota:** `/settings/origins`

## 7. Regras de negócio

1. Nome único por tenant, sem acento na comparação.
2. Excluir origem em uso exige transferência.
3. `PARTE CONTRÁRIA` é semeada mas não é especial — é origem como qualquer outra.
4. Inativar mantém histórico.
5. Só GESTOR escreve.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | CRUD | ~0,3 s |
| integração | duplicidade → 409 | ~0,2 s |
| integração | excluir em uso → 409, com transferência funciona | ~0,4 s |
| integração | RLS entre tenants | ~0,3 s |
| unit | seed idempotente | ~0,1 s |

**Total:** ~1,3 s

## 9. Descobertas

- **Unicidade real exige índice funcional, não `UNIQUE` simples** — mesma correção já aplicada
  em 014/015: regra 1 pede comparação sem acento e case-insensitive, mas `unaccent()` do
  Postgres é `STABLE`, não pode entrar em expressão de índice. Substituído o
  `UNIQUE(tenant_id, name)` da seção 4 por
  `UNIQUE(tenant_id, immutable_unaccent(lower(name)))`, reaproveitando a função
  `immutable_unaccent` criada na migration 014 (não precisou recriar).
- **"Excluir origem em uso exige transferência" (regra 2) não tem como ser real ainda.**
  `customers` só chega na spec 017 (seção 3, "Fora de escopo": "Uso no cadastro de contato →
  017") — nada referencia `origin_id` hoje. Mesma situação já registrada nas specs 014
  (`lawsuit_types`) e 015 (`stages`). Resolvido do mesmo jeito:
  - `DELETE /customer-origins/{id}` é incondicional por enquanto.
  - `POST /customer-origins/transfer` valida `from_id`/`to_id` (distintos, existentes no
    tenant) mas não move nenhum dado real (`transferred_count` sempre `0`) — o contrato fica
    pronto para quando `customers.origin_id` existir.
  - `TransferBeforeDeleteDialog` (listado em "Reutiliza") não foi plugado na tela — mostrar um
    diálogo de transferência antes de excluir seria a UI fingindo uma trava que o backend não
    impõe. Fica para quando a spec 017 der um motivo real.
  - O plano de testes original tinha "excluir em uso → 409, com transferência funciona";
    substituído por testes do que é real hoje: exclusão incondicional funciona, transferência
    com ids válidos retorna 200 (no-op), com ids iguais/inexistentes retorna 422.
- **"Seed idempotente" testado contra o Postgres de verdade, não só como dado estático.**
  Diferente da spec 015 (onde a checagem de unicidade tem uma partição por fase que fazia
  sentido verificar via `ScriptDirectory`), aqui não há partição nenhuma — bastou criar um
  tenant real via `admin_engine` e rodar o `INSERT ... ON CONFLICT DO NOTHING` (mesma SQL da
  migration) duas vezes seguidas, confirmando que o total continua em 8 origens.
- **`FilterBar` (status/q) incluída na tela mesmo não estando em "Reutiliza".** A seção 5 já
  declara `GET /customer-origins?status=&q=` e o CLAUDE.md §6 (contrato de listagem) pede
  filtros vivendo na URL para toda spec de listagem — sem isso, um filtro que o backend já
  suporta ficaria inacessível na UI. Não é um componente novo, só o uso do já existente.
- **Nenhum componente novo** — `CustomerOriginsListPage` reaproveita `DataTable`, `FilterBar`,
  `FormModal`, `ConfirmDialog` (todos já existentes); a spec confirma "Cria: nada".

## 10. Definição de pronto

- [x] Migration `016_customer_origins` aplica e reverte de forma limpa (testado contra
      `rito_test` do zero e contra o banco de dev).
- [x] 8 origens semeadas (seed idempotente, testado contra Postgres real).
- [x] RLS ligado + teste de isolamento entre tenants.
- [x] CRUD completo + endpoint de transferência com contrato pronto para a spec 017.
- [x] 233 testes de integração cobrindo o plano da spec (ajustado conforme Descobertas) —
      100% de cobertura em `app/domain/customer_origins/`.
- [x] Frontend: `CustomerOriginsListPage` reaproveitando `DataTable`/`FilterBar`/`FormModal`/
      `ConfirmDialog` — nenhum componente novo, como a spec previa.
- [x] `make lint` verde (ruff, black, mypy, eslint, tsc, prettier).
- [x] `make test` verde — 233 backend / 55 frontend / 3 e2e, wall-clock 42 s (orçamento 120 s).
- [x] Verificado manualmente em navegador (Playwright ad-hoc, não commitado) — CRUD, filtro,
      duplicidade case/acento-insensível e exclusão funcionando ponta a ponta.

Commit `feat(016): origem de pessoas`
