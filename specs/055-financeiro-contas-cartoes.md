# 055 — Financeiro: contas e cartões

**Fase:** 5 · **Tipo:** feature · **Orçamento:** +4 s
**Depende de:** 054 · **Status:** ⬜ pendente

---

## 1. Objetivo

Onde o dinheiro entra e sai. Contas bancárias e cartões de crédito, com o comportamento
particular do cartão: ciclo de fechamento e vencimento de fatura.

## 2. Escopo

- Tabela `bank_accounts` com 5 tipos
- Tabela `financial_institutions` com ~95 instituições (seed)
- Ciclo e vencimento para cartão
- Saldo inicial e conta padrão
- Cálculo de saldo atual
- Tela `Configurações > Financeiro > Contas e cartões`

## 3. Fora de escopo

- Lançamentos → 056 · Fluxo de caixa → 059 · Fatura de cartão como documento → fora do escopo

## 4. Modelo de dados

```sql
CREATE TYPE account_kind AS ENUM ('CORRENTE','POUPANCA','INVESTIMENTO','CARTAO_CREDITO','OUTRO');

CREATE TABLE financial_institutions (   -- global
  id SMALLINT PRIMARY KEY, name TEXT NOT NULL UNIQUE, compe_code TEXT
);

CREATE TABLE bank_accounts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  kind account_kind NOT NULL,
  name TEXT NOT NULL,
  institution_id SMALLINT REFERENCES financial_institutions(id),
  agency TEXT, account_number TEXT,
  cycle_day SMALLINT,        -- fechamento da fatura (só cartão)
  due_day SMALLINT,          -- vencimento da fatura (só cartão)
  initial_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
  is_default BOOLEAN NOT NULL DEFAULT false,
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name),
  CHECK (kind <> 'CARTAO_CREDITO' OR (cycle_day BETWEEN 1 AND 31 AND due_day BETWEEN 1 AND 31)),
  CHECK (kind =  'CARTAO_CREDITO' OR (cycle_day IS NULL AND due_day IS NULL))
);
CREATE UNIQUE INDEX ux_accounts_default ON bank_accounts (tenant_id)
  WHERE is_default AND is_active;
```
RLS ligado. Migration `055_bank_accounts.py` + seed das instituições.

O índice único parcial garante **uma só conta padrão** por tenant — no banco, não na aplicação.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/bank-accounts?status=&kind=` | financial ≥ READ_ONLY |
| POST/PUT/DELETE | `/api/v1/bank-accounts[/{id}]` | financial = FULL |
| POST | `/api/v1/bank-accounts/{id}/set-default` | financial = FULL |
| GET | `/api/v1/bank-accounts/{id}/balance?at=` | financial ≥ READ_ONLY |
| GET | `/api/v1/financial-institutions?q=` | autenticado |

## 6. Front-end

**Reutiliza:** `DataTable`, `FormModal`, `MoneyField`, `ConfirmDialog`
**Cria:** `BankAccountForm` (campos condicionais por tipo), `InstitutionSelect`,
`AccountBalanceCard`
**Rota:** `/settings/financial?tab=accounts`

## 7. Regras de negócio

1. `CARTAO_CREDITO` **exige** `cycle_day` e `due_day`; os demais tipos não podem tê-los (constraints).
2. Uma só conta padrão ativa por tenant (índice único parcial). Definir nova desmarca a anterior, em transação.
3. Saldo atual = `initial_amount` + entradas − saídas dos lançamentos **pagos** e não internos.
4. Cartão não tem saldo, tem **fatura**: soma dos lançamentos do ciclo corrente.
5. Ciclo do cartão: dia `cycle_day` do mês até o dia anterior do mês seguinte. Dia 31 em mês curto usa o último dia.
6. Conta com lançamento não pode ser excluída — só inativada.
7. Inativar conta padrão exige eleger outra antes → 409.
8. Nome único por tenant.
9. Saldo inicial é imutável depois do primeiro lançamento; alterar exige ajuste por lançamento.
10. Escrita exige `financial_access = FULL`.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | CRUD dos 5 tipos | ~0,5 s |
| integração | cartão sem ciclo → 422 | ~0,2 s |
| integração | conta corrente com ciclo → 422 | ~0,2 s |
| integração | **só uma padrão ativa** (tentativa concorrente) | ~0,4 s |
| integração | trocar padrão desmarca a anterior | ~0,3 s |
| integração | excluir conta com lançamento → 409 | ~0,3 s |
| integração | inativar padrão sem substituta → 409 | ~0,3 s |
| integração | saldo ignora internos e não pagos | ~0,4 s |
| unit | ciclo do cartão com dia 31 em fevereiro | ~0,2 s |
| integração | saldo inicial imutável após lançamento | ~0,3 s |
| frontend | formulário alterna campos por tipo | ~0,4 s |

**Total:** ~3,5 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Unicidade da conta padrão garantida no banco · Commit `feat(055): financeiro — contas e cartões`
