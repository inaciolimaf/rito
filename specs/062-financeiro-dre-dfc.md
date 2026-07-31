# 062 — Financeiro: relatórios DRE e DFC

**Fase:** 6 · **Tipo:** feature · **Orçamento:** +5 s
**Depende de:** 061 · **Status:** ⬜ pendente

---

## 1. Objetivo

Demonstração de Resultado e Demonstração de Fluxo de Caixa agrupadas pelos 10 grupos DRE. É o
relatório que o contador pede e o sócio usa para decidir.

## 2. Escopo

- DRE por competência
- DFC por movimentação de caixa
- Comparativo entre períodos
- Detalhamento por categoria dentro do grupo
- Export xlsx e pdf

## 3. Fora de escopo

- BI de custo por processo → 077 · Conciliação bancária (fora do escopo)

## 4. Modelo de dados

Nenhuma tabela nova. Índice de apoio:

```sql
CREATE INDEX ix_tx_dre ON transactions (tenant_id, competence, category_id)
  WHERE NOT is_internal AND kind <> 'TRANSFERENCIA';
```
Migration `062_dre_index.py`.

## 5. Contratos de API

| Método | Rota |
|---|---|
| GET | `/api/v1/reports/dre?from=&to=&compare_to=&cost_center_id=` |
| GET | `/api/v1/reports/dfc?from=&to=&account_id=` |
| POST | `/api/v1/reports/dre/export` · `/dfc/export` |

Estrutura do DRE:
```
(+) 1. Receitas                          R$ ...
(−) 0. Deduções da receita bruta         R$ ...
(=) Receita líquida                      R$ ...
(−) 2. Folha de pagamento
(−) 3. Encargos sociais
(−) 4. Tributos
(−) 5. Despesas fixas
(−) 6. Despesas variáveis
(−) 7. Despesas bancárias
(−) 8. Marketing e comercial
(=) Resultado operacional
(−) 9. Distribuição de lucros
(=) Resultado líquido
```

## 6. Front-end

**Reutiliza:** `DataTable`, `FilterBar`, `MoneyField`
**Cria:** `DreReport` (linhas hierárquicas expansíveis), `DfcReport`, `PeriodComparator`,
`ReportExportButton`
**Rota:** `/transactions?tab=reports`

## 7. Regras de negócio

1. **DRE usa `competence`**; DFC usa `payment_date`. Confundir os dois é o erro clássico — cada relatório tem sua data.
2. DFC só considera lançamentos **pagos**; DRE considera todos os do período de competência, pagos ou não.
3. Transferência **não** entra em nenhum dos dois — não é resultado nem fluxo líquido.
4. Lançamento interno fora de ambos.
5. Grupo sem movimento aparece zerado, não some — a estrutura é fixa.
6. Cada grupo expande para as categorias, e a categoria expande para os lançamentos.
7. Comparativo mostra período atual, anterior e variação absoluta e percentual.
8. Filtro por centro de custo aplica ao DRE inteiro.
9. Soma dos grupos = resultado líquido, sempre. Há teste que valida a identidade contábil.
10. Export preserva a hierarquia (xlsx com agrupamento, pdf com indentação).
11. Exige `financial_access ≥ READ_ONLY`.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | **DRE fecha: soma dos grupos = resultado líquido** | ~0,5 s |
| integração | DRE usa competência, não pagamento | ~0,4 s |
| integração | DFC usa pagamento e só pagos | ~0,4 s |
| integração | transferência fora dos dois | ~0,3 s |
| integração | interno fora dos dois | ~0,3 s |
| integração | grupo sem movimento aparece zerado | ~0,2 s |
| integração | detalhamento por categoria soma o grupo | ~0,4 s |
| integração | comparativo calcula variação | ~0,4 s |
| integração | filtro por centro de custo | ~0,3 s |
| integração | `financial_access = NONE` → 403 | ~0,2 s |
| integração | export xlsx com hierarquia | ~0,4 s |
| frontend | linhas expandem e recolhem | ~0,4 s |

**Total:** ~4,2 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Identidade contábil testada · Commit `feat(062): financeiro — DRE e DFC`
