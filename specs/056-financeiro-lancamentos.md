# 056 — Financeiro: lançamentos

**Fase:** 5 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 055 · **Status:** ⬜ pendente

---

## 1. Objetivo

O coração do módulo financeiro. Receita, despesa e transferência entre contas, com a regra que
mais causa erro em sistema jurídico: **o tipo do lançamento tem que casar com o tipo da categoria**.

## 2. Escopo

- Tabela `transactions`
- Três tipos: RECEITA, DESPESA, TRANSFERÊNCIA
- Validação cruzada tipo × categoria
- Vínculo com cliente e processo
- Competência derivada do vencimento
- Baixa (registro de pagamento)

## 3. Fora de escopo

- Recorrência e parcelamento → 057 · Registro interno e anexos → 058
- Dashboard → 059 · Inadimplência → 061

## 4. Modelo de dados

```sql
CREATE TYPE transaction_kind AS ENUM ('RECEITA','DESPESA','TRANSFERENCIA');

CREATE TABLE transactions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  kind transaction_kind NOT NULL,
  user_id UUID NOT NULL REFERENCES users(id),         -- responsável
  debit_account_id  UUID REFERENCES bank_accounts(id), -- conta de saída/origem
  credit_account_id UUID REFERENCES bank_accounts(id), -- destino (só transferência)
  category_id UUID REFERENCES financial_categories(id),
  cost_center_id UUID REFERENCES cost_centers(id),
  customer_id UUID REFERENCES customers(id),
  lawsuit_id UUID REFERENCES lawsuits(id),
  description TEXT,
  amount NUMERIC(14,2) NOT NULL CHECK (amount > 0),
  due_date DATE NOT NULL,
  payment_date DATE,
  competence DATE NOT NULL,                            -- 1º dia do mês de competência
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (kind <> 'TRANSFERENCIA' OR (credit_account_id IS NOT NULL
         AND debit_account_id IS NOT NULL AND debit_account_id <> credit_account_id)),
  CHECK (kind =  'TRANSFERENCIA' OR (category_id IS NOT NULL AND cost_center_id IS NOT NULL)),
  CHECK (lawsuit_id IS NULL OR customer_id IS NOT NULL),
  CHECK (payment_date IS NULL OR payment_date <= CURRENT_DATE)
);
CREATE INDEX ix_tx_due        ON transactions (tenant_id, due_date DESC);
CREATE INDEX ix_tx_payment    ON transactions (tenant_id, payment_date DESC) WHERE payment_date IS NOT NULL;
CREATE INDEX ix_tx_competence ON transactions (tenant_id, competence DESC);
CREATE INDEX ix_tx_lawsuit    ON transactions (lawsuit_id) WHERE lawsuit_id IS NOT NULL;
CREATE INDEX ix_tx_customer   ON transactions (tenant_id, customer_id) WHERE customer_id IS NOT NULL;
CREATE INDEX ix_tx_open       ON transactions (tenant_id, due_date) WHERE payment_date IS NULL;
```
RLS ligado. Migration `056_transactions.py`.

Quatro constraints codificam as regras críticas **no banco**, não só na aplicação.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/transactions?<filtros>` | financial ≥ READ_ONLY |
| POST/PUT/DELETE | `/api/v1/transactions[/{id}]` | financial = FULL |
| POST | `/api/v1/transactions/{id}/pay` → `{payment_date}` | financial = FULL |
| POST | `/api/v1/transactions/{id}/unpay` | financial = FULL |

## 6. Front-end

**Reutiliza:** `FormModal`, `EntityPicker`, `MoneyField`, `DataTable`, `ConfirmDialog`
**Cria:** `TransactionForm` (campos condicionais pelos 3 tipos), `CategorySelect`
(filtra por tipo), `PayTransactionDialog`
**Rota:** modal sobre `/transactions`

## 7. Regras de negócio

1. **RECEITA só aceita categoria de tipo RECEITA; DESPESA só de DESPESA.** Violação → 422 com mensagem explícita. Esta é a regra que mais quebra integração.
2. TRANSFERÊNCIA exige conta de origem e destino **diferentes**, e não usa categoria nem centro de custo.
3. `lawsuit_id` exige `customer_id` (constraint) — vincular processo sem cliente é inconsistente.
4. `description` é convertida para **MAIÚSCULAS** na gravação (paridade com o ADVBOX).
5. `competence` é derivada de `due_date` (primeiro dia daquele mês) quando não informada.
6. `amount` sempre positivo. O sinal vem do `kind`, não do valor.
7. `payment_date` não pode ser futura (constraint).
8. Baixa preenche `payment_date`; estornar limpa. Ambas exigem `FULL`.
9. Transferência move saldo entre contas e **não** aparece no DRE — é movimentação, não resultado.
10. Excluir lançamento pago exige estornar antes → 409.
11. Vínculo com processo alimenta o painel financeiro do processo (024).
12. Valor com vírgula decimal na UI; a API trafega número.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | criar receita, despesa e transferência | ~0,5 s |
| integração | **receita com categoria de despesa → 422** | ~0,3 s |
| integração | **despesa com categoria de receita → 422** | ~0,3 s |
| integração | transferência com contas iguais → 422 | ~0,2 s |
| integração | transferência com categoria → 422 | ~0,2 s |
| integração | processo sem cliente → 422 | ~0,2 s |
| integração | descrição vira maiúsculas | ~0,2 s |
| integração | competência derivada do vencimento | ~0,2 s |
| integração | amount zero ou negativo → 422 | ~0,2 s |
| integração | pagamento futuro → 422 | ~0,2 s |
| integração | baixa e estorno | ~0,3 s |
| integração | excluir pago → 409 | ~0,2 s |
| integração | transferência move saldo das duas contas | ~0,4 s |
| integração | `READ_ONLY` não escreve → 403 | ~0,2 s |
| integração | RLS entre tenants | ~0,3 s |
| frontend | formulário alterna pelos 3 tipos | ~0,5 s |
| frontend | categoria filtra pelo tipo escolhido | ~0,4 s |

**Total:** ~4,8 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Regra tipo × categoria testada nos dois sentidos · Commit `feat(056): financeiro — lançamentos`
