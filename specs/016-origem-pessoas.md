# 016 — Origem de pessoas

**Fase:** 1 · **Tipo:** feature · **Orçamento:** +2 s
**Depende de:** 011 · **Status:** ⬜ pendente

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

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Commit `feat(016): origem de pessoas`
