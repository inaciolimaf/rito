# 058 — Financeiro: registro interno e anexos

**Fase:** 5 · **Tipo:** feature · **Orçamento:** +3 s
**Depende de:** 056 · **Status:** ⬜ pendente

---

## 1. Objetivo

Dois complementos práticos: o lançamento que existe para controle mas **não** move saldo
(honorário a combinar, provisão, reembolso pendente), e o comprovante anexado.

## 2. Escopo

- Flag `is_internal`
- Anexos por lançamento (reusa `attachments` de 035)
- Filtro por interno
- Exclusão do interno de todos os cálculos de saldo

## 3. Fora de escopo

- Storage definitivo → 063 · OCR de comprovante → 091

## 4. Modelo de dados

```sql
ALTER TABLE transactions
  ADD COLUMN is_internal BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN internal_note TEXT;

CREATE INDEX ix_tx_effective ON transactions (tenant_id, due_date)
  WHERE NOT is_internal;
```
Migration `058_internal_transactions.py`.

O índice parcial é o que mantém as consultas de saldo rápidas — a maioria das queries filtra
`NOT is_internal`.

## 5. Contratos de API

`POST`/`PUT /transactions` passam a aceitar `is_internal` e `internal_note`.
`GET /transactions` ganha `internal=true|false|all` (padrão: `all`).

| Método | Rota |
|---|---|
| POST | `/api/v1/transactions/{id}/attachments` |
| GET | `/api/v1/transactions/{id}/attachments` |

## 6. Front-end

**Reutiliza:** `FileDropzone`, `AttachmentList` (de 035), `FormModal`
**Cria:** `InternalToggle` (com explicação inline), `InternalBadge`

## 7. Regras de negócio

1. Lançamento interno **não entra** em: saldo da conta, fluxo de caixa, DRE, DFC, receita/despesa
   prevista ou realizada, nem inadimplência.
2. Ele **entra** na listagem, nos totais do período filtrado (marcado como tal) e no painel
   financeiro do processo — é informação de gestão, não de caixa.
3. Converter interno em efetivo é permitido e recalcula os saldos.
4. Converter efetivo **pago** em interno → 409. Estorne primeiro.
5. Interno pode ter `payment_date` (registro de que "foi acertado"), sem afetar saldo.
6. Anexos usam a tabela genérica `attachments` com `attached_to_type = 'transaction'`.
7. Limite de 20 anexos por lançamento.
8. Excluir lançamento remove os anexos dele.
9. Filtro padrão da listagem mostra **todos**, com o interno visualmente distinto.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | interno não altera saldo da conta | ~0,4 s |
| integração | interno fora do fluxo de caixa | ~0,3 s |
| integração | interno aparece na listagem e no total do período | ~0,3 s |
| integração | interno aparece no painel do processo | ~0,3 s |
| integração | converter interno → efetivo recalcula saldo | ~0,4 s |
| integração | converter pago → interno → 409 | ~0,2 s |
| integração | anexo vinculado e listado | ~0,3 s |
| integração | 21º anexo → 422 | ~0,2 s |
| integração | excluir lançamento remove anexos | ~0,3 s |
| frontend | badge de interno e explicação | ~0,3 s |

**Total:** ~3,0 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Interno fora de todo cálculo de caixa · Commit `feat(058): financeiro — registro interno e anexos`
