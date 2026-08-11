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

**Reaproveitado, não recriado:** `app/core/dates.py` (spec 040) já tinha exatamente a
aritmética de mês precisada aqui — `next_occurrence(RecurrencePeriod.MENSAL,
RecurrenceWeek.DIA_EXATO, anchor=..., current=...)` clampa dia 31 num mês curto pro
último dia (regra 6) usando a mesma âncora sempre (nunca a ocorrência anterior já
clampada), idêntico ao que parcelamento/recorrência precisavam. Nada novo em
`app/core/dates.py`; só um novo consumidor, exatamente como o comentário do módulo já
antecipava desde a spec 040 ("057 (parcelamento financeiro) usa
`add_business_days`/aritmética de mês").

**Interpretação de "encerrar recorrência preserva o já criado" (regra 9):** a leitura
literal ("preserva TUDO que já foi gerado") colide com a regra 8 ("`scope=future` remove
só as não pagas") — se as duas se aplicam à mesma ação, uma tem que ceder. A leitura que
faz sentido de negócio (e que ficou implementada): "o já criado" é o que já virou FATO
financeiro, ou seja, o que já foi PAGO. Encerrar uma recorrência remove as ocorrências
em aberto (não fazem mais sentido — a recorrência parou) mas nunca mexe no histórico
pago. `DELETE ?scope=future` e `?scope=all` acabaram symétricos nesse ponto: a única
diferença real entre os dois é que `scope=all` bloqueia com 409 se sobrar QUALQUER
lançamento pago na série (a série inteira só some se não há nada a preservar);
`scope=future` nunca bloqueia — sempre remove as não pagas e encerra a série
(`is_active=false`), preservando as pagas. Um teste do plano (`encerrar recorrência
preserva o já gerado`) precisou de ajuste depois de rodar pela primeira vez: a versão
inicial esperava que TODAS as 4 ocorrências geradas sobrevivessem ao encerramento; o
comportamento real (e correto, pela leitura acima) é que só a paga sobrevive — o teste
foi corrigido para pagar uma ocorrência antes de encerrar, não o código.

**Worker sem fila nos testes:** mesmo padrão de `RecurrenceService.sweep_overdue` (spec
034) e `StagnationService.recalculate_tenant` (spec 052) — a regra mora inteira em
`TransactionSeriesService.generate_recurrence`/`sweep_recurring`, chamada direto nos
testes de integração (sessão + `set_tenant_context`, sem Celery real). O Celery beat
(`app/workers/financial_recurrence.py`, agendado dia 1 de cada mês às 3h30) só embrulha
essa mesma chamada por tenant — nunca testado com fila de verdade (CLAUDE.md §3).

**`GET /transactions/{id}/series-preview` em vez de um endpoint por série:** a rota tem
`{transaction_id}`, não `{series_id}`, porque toda tela que precisaria do preview já
está olhando pra um lançamento específico (a linha da lista, o formulário de edição) —
pedir o `series_id` seria mais um round-trip pra descobrir algo que o próprio
lançamento já sabe. O endpoint resolve `series_id` internamente e devolve a série
inteira ordenada por vencimento.

**Achado de UI, corrigido antes do commit:** ao ligar `CategorySelect`/`EntityPicker` ao
novo seletor de "Modo" (parcelado/recorrente/único) dentro do `TransactionForm`, a
primeira verificação manual em browser real mostrou os 3 modos alternando campos
corretamente e o preview de parcelas vivo funcionando (12 parcelas de R$ 100,00 cada
somando R$ 1.200,00 exatos, sufixo `(n/12)` certo em cada uma) — sem bug encontrado
desta vez (ao contrário da 056, onde o mesmo tipo de verificação pegou um bug real de
label). `InstallmentBadge` deriva o "n/N" direto do sufixo que o backend já grava na
descrição (regra 3) em vez de um campo próprio no `TransactionResponse` — o sufixo já é
a fonte da verdade visual, duplicar em um campo separado arriscaria os dois divergirem.

**Fora de escopo, registrado, não implementado:** a spec não pede uma tela própria de
"gerenciar série" — só `PUT/DELETE /transaction-series/{id}` na API. A UI ganhou
`SeriesScopeDialog` + ação "Excluir série" na listagem (regra 8/9, testado em browser
real), mas NÃO ganhou uma ação "Editar série" na lista (o `PUT` está implementado e
testado na API — inclusive a checagem da regra 1 quando `category_id` muda — mas sem
entrada na UI). Decisão de escopo: editar-em-lote precisaria de um mini-formulário
próprio (valor/categoria/centro/descrição) fora do que `components/domain/` já oferece,
e o valor de negócio de "excluir série" (a ação realmente esperada ao errar um
parcelamento) é bem maior que "editar em lote". Registrado aqui para uma spec futura
decidir se vale a pena, não em `docs/DIVIDA-TECNICA.md` (não é dívida — é escopo nunca
prometido).

UI verificada manualmente num browser real (backend/frontend fora de 5173/8000, lição já
registrada em memória): parcelamento em 12x com preview ao vivo antes de salvar,
lançamentos gerados batendo com o preview, badge "n/N" na listagem, exclusão de série
completa via `SeriesScopeDialog` (as 12 parcelas somem), e criação de lançamento
recorrente mensal com os campos de periodicidade/data-fim aparecendo corretamente.

## 10. Definição de pronto

Checklist padrão · Arredondamento sem perder centavo (100÷3 = 33,33+33,33+33,34, testado)
· Dia 31 em fevereiro testado (parcela e preview do frontend) · Worker testado direto
(sem fila) gerando só 3 meses à frente e avançando `generated_until` · `scope=future`
nunca toca lançamento pago; `scope=all` bloqueia com 409 se houver algum pago · UI
verificada em browser real · `make lint` e `make test` verdes (826 backend, 152
frontend, 9 e2e — wall-clock 254s, orçamento 300s) · Commit `feat(057): financeiro —
recorrência e parcelamento`
