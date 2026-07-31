# 057 — Financeiro: recorrência e parcelamento

**Fase:** 5 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 056 · **Status:** ⬜ pendente

---

## 1. Objetivo

Honorário mensal recorrente e contrato parcelado em N vezes. São coisas diferentes: recorrência
é indefinida e gera conforme o tempo passa; parcelamento tem fim e gera tudo de uma vez.

## 2. Escopo

- Recorrência de lançamento
- Parcelamento em até 100 vezes
- Edição da série (só futuras ou todas)
- Encerramento de série
- Identificação visual de parcela (3/12)

## 3. Fora de escopo

- Cobrança e boleto (fora do escopo — sem Asaas) · Régua de inadimplência → 061

## 4. Modelo de dados

```sql
CREATE TYPE financial_recurrence AS ENUM
  ('MENSAL','BIMESTRAL','TRIMESTRAL','SEMESTRAL','ANUAL');

CREATE TABLE transaction_series (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  is_installment BOOLEAN NOT NULL,          -- true = parcelado, false = recorrente
  recurrence financial_recurrence,
  total_installments SMALLINT,
  until_date DATE,
  generated_until DATE,
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (is_installment = (total_installments IS NOT NULL)),
  CHECK (total_installments IS NULL OR total_installments BETWEEN 2 AND 100)
);

ALTER TABLE transactions
  ADD COLUMN series_id UUID REFERENCES transaction_series(id),
  ADD COLUMN installment_number SMALLINT;
CREATE INDEX ix_tx_series ON transactions (series_id, installment_number)
  WHERE series_id IS NOT NULL;
```
RLS ligado. Migration `057_transaction_series.py`.

## 5. Contratos de API

`POST /api/v1/transactions` passa a aceitar:
```json
{ "installment": {"count": 12} }
{ "recurrence": {"period": "MENSAL", "until_date": "2027-12-31"} }
```

| Método | Rota |
|---|---|
| GET | `/api/v1/transaction-series/{id}` |
| PUT | `/api/v1/transaction-series/{id}?scope=future\|all` |
| DELETE | `/api/v1/transaction-series/{id}?scope=future\|all` |
| GET | `/api/v1/transactions/{id}/series-preview` |

## 6. Front-end

**Reutiliza:** `FormModal`, `ConfirmDialog`, `MoneyField`
**Cria:** `InstallmentFields`, `FinancialRecurrenceFields`, `SeriesScopeDialog`
(escolher entre "só esta e as futuras" e "todas"), `InstallmentBadge`
**Rota:** dentro do `TransactionForm`

## 7. Regras de negócio

1. **Parcelamento gera todas as parcelas na criação**, com vencimentos mensais a partir da data informada.
2. Divisão do valor: `amount ÷ count`, arredondado para 2 casas; **a diferença de centavos vai na última parcela**. A soma tem que bater exatamente com o total.
3. Descrição da parcela recebe sufixo ` (3/12)`.
4. **Recorrência não gera tudo antecipadamente** — um worker mensal gera os próximos 3 meses, mantendo `generated_until`.
5. Recorrência sem `until_date` é indefinida e continua gerando até ser encerrada.
6. Vencimento em dia inexistente (31 em fevereiro) usa o **último dia do mês** — reutiliza `app/core/dates.py` de 040.
7. Editar série: `scope=future` afeta as não pagas a partir da atual; `scope=all` afeta todas as não pagas. **Parcela paga nunca é alterada.**
8. Excluir série com parcela paga → 409 em `scope=all`; `scope=future` remove só as não pagas.
9. Encerrar recorrência para a geração e preserva o já criado.
10. Cada lançamento da série é independente para baixa.
11. Máximo de 100 parcelas.
12. Recorrência aceita só os 5 períodos do enum — diária e semanal não fazem sentido aqui, diferente das tarefas (034).

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | 12x gera 12 parcelas com vencimentos certos | ~0,5 s |
| unit | **soma das parcelas = total, com resto na última** | ~0,2 s |
| unit | 100,00 ÷ 3 = 33,33 + 33,33 + 33,34 | ~0,1 s |
| integração | sufixo (n/N) na descrição | ~0,2 s |
| integração | dia 31 em fevereiro vai para o último dia | ~0,3 s |
| integração | recorrência gera só 3 meses à frente | ~0,4 s |
| integração | worker avança `generated_until` | ~0,4 s |
| integração | `scope=future` não toca parcela paga | ~0,4 s |
| integração | `scope=all` não toca parcela paga | ~0,4 s |
| integração | excluir série com paga → 409 | ~0,3 s |
| integração | encerrar recorrência preserva o gerado | ~0,3 s |
| integração | 101 parcelas → 422 | ~0,2 s |
| frontend | preview das parcelas antes de salvar | ~0,4 s |

**Total:** ~4,1 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Arredondamento sem perder centavo · Commit `feat(057): financeiro — recorrência e parcelamento`
