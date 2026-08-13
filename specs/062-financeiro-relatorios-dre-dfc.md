# 062 — Financeiro: relatórios DRE e DFC

**Fase:** 6 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 061 · **Status:** ✅ concluída

---

## 1. Objetivo

O escritório precisa fechar o mês olhando o resultado agrupado, não linha por linha do
razão. Esta spec entrega a DRE (regime de competência) e a DFC (regime de caixa), as
duas agrupadas pelos mesmos 10 grupos DRE (spec 054), por período livre.

## 2. Escopo

- DRE: receita e despesa por grupo DRE, filtradas por `competence`, resultado líquido.
- DFC: mesmo agrupamento, filtrado por `payment_date` — só o que efetivamente
  movimentou caixa no período.
- Filtro por período (`from`/`to`) e por conta.
- Export xlsx/pdf de qualquer um dos dois relatórios.

## 3. Fora de escopo

- DFC contábil por atividades (operacional/investimento/financiamento) — o Rito não
  modela essas categorias; a "DFC" aqui é o mesmo agrupamento por grupo DRE em regime
  de caixa, simplificação já esperada para um sistema de gestão (não um ERP contábil).
- Comparação entre períodos (mês atual × anterior) — cabe numa spec de BI futura
  (074–078) se vier a ser pedida.
- DRE/DFC por centro de custo — só por grupo DRE (o que a spec pede).

## 4. Modelo de dados

Nenhuma tabela nova. Os dois relatórios são agregações sobre `transactions` (spec 056)
join `financial_categories` (spec 054) → `dre_groups` (spec 054), já existentes.

## 5. Contratos de API

| Método | Rota | Entrada | Saída | Autorização |
|---|---|---|---|---|
| GET | `/api/v1/financial-reports/dre?from=&to=&account_id=` | query | `200 {rows[], total_receita, total_despesa, resultado}` | financial ≥ READ_ONLY |
| GET | `/api/v1/financial-reports/dfc?from=&to=&account_id=` | query | idem, regime de caixa | financial ≥ READ_ONLY |
| POST | `/api/v1/financial-reports/export` | `{report, from, to, account_id, format}` | arquivo xlsx/pdf | financial ≥ READ_ONLY |

`report` ∈ `dre`/`dfc`. Erros: `422` se `to < from`.

## 6. Front-end

**Componentes reutilizados:** `DataTable` (linhas por grupo), `StatCard` (resultado
líquido), `FilterBar` (período, conta)
**Componentes criados:** `FinancialReportPage` (alterna DRE/DFC por aba) — não há
estrutura equivalente hoje (dashboard, spec 059, mostra cards/gráfico, não uma tabela
de razão agrupado); menos de 3 usos, não vai para `components/domain/`.
**Rota:** `/transactions?tab=reports` (3ª aba do módulo Financeiro, ao lado de
Lançamentos e Inadimplência — o item "Relatórios" do menu é da spec 071, relatórios
de produtividade/BI, escopo diferente)
**Estados:** loading, vazio (sem lançamento no período), erro, sem permissão

## 7. Regras de negócio

1. DRE agrupa por `dre_group_id` da categoria do lançamento, no período por
   `competence` (regime de competência, fixo — não segue o seletor do dashboard).
2. DFC agrupa igual, mas no período por `payment_date` — lançamento sem `payment_date`
   preenchida nunca entra na DFC.
3. Transferência (`kind = TRANSFERENCIA`) e lançamento interno (`is_internal`) nunca
   entram em nenhum dos dois — mesmo filtro dos demais relatórios financeiros
   (dashboard, spec 059; inadimplência, spec 061).
4. Total de cada grupo = soma de RECEITA − soma de DESPESA dos lançamentos daquele
   grupo no período (o `type` da categoria pode divergir da `nature` do grupo, spec
   054 regra 2 — o valor exibido é sempre o líquido real do grupo, nunca assume que
   todo lançamento do grupo tem a mesma natureza).
5. `total_receita`/`total_despesa`/`resultado` do relatório são a soma exata dos
   grupos — a soma bate com o razão (aceite): `resultado == total_receita -
   total_despesa` e ambos batem com `SUM(amount)` das mesmas transações fora do
   agrupamento.
6. Grupo sem lançamento no período não aparece na resposta.
7. Filtro por conta (`account_id`) restringe a `debit_account_id` (mesmo padrão do
   dashboard) — transações sem conta vinculada nunca aparecem quando o filtro é usado.
8. Export respeita os mesmos filtros da tela (período, conta, tipo de relatório), não
   a paginação (o relatório inteiro cabe numa página, não pagina).

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| integração | DRE agrupa por grupo e bate com o razão (seed determinístico) | `tests/integration/test_financial_reports.py` | ~0,4 s |
| integração | DFC só conta lançamento pago, por `payment_date` | idem | ~0,4 s |
| integração | grupo com categorias de naturezas opostas soma líquido corretamente | idem | ~0,3 s |
| integração | transferência e interno nunca entram (DRE e DFC) | idem | ~0,3 s |
| integração | filtro por conta restringe corretamente | idem | ~0,3 s |
| integração | grupo sem lançamento não aparece | idem | ~0,2 s |
| integração | `to < from` → 422 | idem | ~0,2 s |
| integração | export xlsx e pdf geram arquivo não vazio | idem | ~0,3 s |
| RLS | tenant A não vê lançamento de tenant B no relatório | idem | ~0,3 s |
| frontend | alterna DRE/DFC, aplica filtro de período | `src/features/financial/*.test.tsx` | ~0,3 s |

**Total estimado:** ~3,4 s
**Fixtures externas:** nenhuma. Sem chamada de rede.

## 9. Descobertas

- Nenhuma tabela nova foi necessária — os dois relatórios são só uma leitura diferente
  do razão (`transactions` join `financial_categories` join `dre_groups`), então a
  spec não trouxe migration.
- A rota `/reports/financial` do rascunho inicial foi trocada por
  `/transactions?tab=reports` (3ª aba do módulo Financeiro) — o item "Relatórios" do
  menu lateral é reservado para a spec 071 (produtividade/BI), escopo diferente deste.

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as regras de negócio com teste
- [x] `make test` verde e wall-clock < 300 s (265 s)
- [x] `make lint` verde
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `feat(062): financeiro — relatórios DRE e DFC`
