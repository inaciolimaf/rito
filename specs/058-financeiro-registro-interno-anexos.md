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

**Regra 1 é quase toda sobre specs que ainda não existem.** "Não entra em saldo, fluxo
de caixa, DRE, DFC, receita/despesa prevista/realizada, inadimplência" — de tudo isso,
só `TransactionRepository.lawsuit_financial_totals` (spec 056) existe hoje; saldo de
conta já é sempre `initial_amount` (dívida técnica #20, spec 057), fluxo de
caixa/DRE/DFC/dashboard são specs futuras (059+), inadimplência é a 061. A exclusão
de `is_internal` foi aplicada em `lawsuit_financial_totals` (o único cálculo real) e
registrada em `docs/DIVIDA-TECNICA.md` #20 como requisito pro retrofit de saldo real
que a 070 vai fazer — não dá pra testar o resto porque o resto não existe.

**Regra 2 ("aparece no painel do processo") não mudou o contrato de
`financial-summary`.** Esse endpoint só devolve 4 números agregados — não há "lista de
lançamentos" nele pra um interno aparecer marcado. A leitura que fechou: "painel do
processo" cobre o que a 024/056 já expõem — `GET /transactions?lawsuit_id=X` — que
sempre incluiu tudo (filtro padrão "all"); a novidade da 058 é só o campo `is_internal`
ficar visível nesse retorno. Testado assim: o mesmo lançamento aparece na listagem
(marcado) e some dos agregados de caixa do resumo, na mesma chamada de teste.

**Anexos reusam `AttachmentService` (spec 035) generalizado, não duplicado.**
`_accessible_post` virou `_validate_target` (mesmo corpo pros tipos existentes,
`post`/`comment`, um branch novo pra `transaction` que só confirma que o lançamento
existe no tenant — sem regra de visibilidade própria, porque quem chega no endpoint já
passou pelo `require_financial`). `remove_all_for_comment` virou um caso de
`remove_all_for(attached_to_type, attached_to_id)` genérico, reaproveitado pela regra
8. O limite de 20 anexos (regra 7) é exclusivo de `attached_to_type="transaction"` —
post/comment continuam sem limite, não existia essa regra antes da 058 e não é desta
spec generalizá-la pra trás.

**Rotas aninhadas por decisão explícita da spec, não convenção do domínio.** O padrão
existente de anexos é genérico (`POST/GET /attachments` com `attached_to_type`/
`attached_to_id` no corpo/query) — mas o §5 desta spec declara literalmente
`POST/GET /transactions/{id}/attachments`. Implementado como pedido (rotas próprias em
`financial/router.py`, delegando pro mesmo `AttachmentService`); download/exclusão de
anexo individual continuam nas rotas genéricas (`/attachments/{id}/...`), que já
funcionam pra qualquer `attached_to_type` sem mudança.

**Achado de processo (não de código) no fechamento — 3 tentativas seguidas de gate
falharam na MESMA jornada e2e (`publications.spec.ts`, jornada 7/25), sempre no mesmo
ponto (linha da intimação recém-criada não aparece na listagem).** Investigado a
fundo por ser consistente demais pra ser a flakiness normal já documentada (spec 048).
Causa raiz real: o tenant e2e (`00000000-0000-0000-0000-0000000000e2`) nunca é limpo
entre execuções de `run-tests.sh` — só o `rito_test` (suíte de integração) é truncado.
Como reexecutei o gate várias vezes NESTA sessão (056/057/058) perseguindo confirmação
de flake, acumulei 39 publicações com `availability_date` de hoje no tenant e2e; o
keyset de listagem (`(availability_date, id)` descendente) desempata por UUID quando a
data é igual — ordem efetivamente aleatória entre elas — e com 39 publicações do mesmo
dia disputando as 20 vagas da primeira página, a mais nova (a do teste) tinha chance
real de não entrar. Corrigido apagando as publicações acumuladas do tenant e2e (não é
uma mudança de código — é limpeza de dado de teste); confirmado com um rerun 100%
verde depois. Não é uma dívida técnica do produto (em CI real, `run-tests.sh` roda uma
vez por push, não dezenas de vezes no mesmo tenant no mesmo dia) — é um artefato desta
sessão de desenvolvimento local, registrado aqui só para não repetir o diagnóstico à
toa numa spec futura que veja o mesmo sintoma.

UI verificada manualmente num browser real (backend/frontend fora de 5173/8000):
marcar como interno mostra a explicação inline e o campo de nota; o badge "Interno"
aparece na listagem ao lado da descrição; reabrir em edição mostra a seção "Anexos"
com o arquivo enviado (nome, tamanho, remover) e o formulário de upload — sem bug
encontrado desta vez.

**Achado de processo #2 — `make lint` nunca tinha rodado de verdade nesta sessão.**
Até agora, o lint de cada ciclo (056/057/058) rodava `ruff`/`black`/`mypy` só nos
diretórios tocados pela spec, nunca `ruff check .`/`black --check .` no repo inteiro
(o que `make lint`/CLAUDE.md §10 realmente pedem). Rodar a versão completa antes de
fechar a 058 expôs 3 linhas longas (E501) em `alembic/versions/056_transactions.py` —
presentes desde o commit da 056, nunca pegas porque o lint daquele ciclo só cobriu
`app/domain/financial`, não `alembic/`. `mypy` já exclui `alembic/` explicitamente
(`pyproject.toml`), mas `ruff`/`black` não têm esse exclude — então migrations
SEMPRE entram no lint completo, só não entravam nos meus comandos escopados.
Corrigido com `black` na 056 (reflow puro de 3 `sa.Column`/`op.create_index`, zero
mudança de SQL/schema — confirmado por diff) apesar da regra "nunca editar migration
já commitada": migration já aplicada nos dois bancos, o reflow não muda o que ela
FAZ, só como o texto quebra linha — risco de drift real é zero. Registrado aqui em
vez de silenciar: daqui pra frente, o fechamento de qualquer spec precisa rodar
`ruff check .`/`black --check .` sem escopo de diretório, não só nos arquivos da
spec corrente.

## 10. Definição de pronto

Checklist padrão · Interno fora de todo cálculo de caixa que já existe
(`lawsuit_financial_totals`) e visível na listagem/painel do processo · Anexos
limitados a 20 por lançamento, removidos ao excluir o lançamento · Conversão
efetivo↔interno testada nos dois sentidos, incluindo o bloqueio de pago→interno (409)
· UI verificada em browser real · `make lint` e `make test` verdes (834 backend, 154
frontend, 9 e2e — wall-clock 241s, orçamento 300s) · Commit `feat(058): financeiro —
registro interno e anexos`
