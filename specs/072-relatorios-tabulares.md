# 072 — Relatórios tabulares

**Fase:** 7 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 071 · **Status:** ⬜ pendente

---

## 1. Objetivo

Sete relatórios operacionais que respondem perguntas objetivas do dia a dia, com filtro e
export. Diferente do BI, aqui é lista, não gráfico — e é sempre tempo real.

## 2. Escopo

Sete relatórios: Produtividade · Tarefas atrasadas · Registros de acesso · Novos clientes ·
Novos processos · Processos ganhos · Processos perdidos.

Mais: pauta de audiências, relatório de partes contrárias, filtros comuns e export.

## 3. Fora de escopo

- BI → 074–077 · Text-to-SQL → 089

## 4. Modelo de dados

Nenhuma tabela nova. Índices que faltam:

```sql
CREATE INDEX ix_lawsuits_outcome_date ON lawsuits (tenant_id, outcome, closure_date)
  WHERE outcome IS NOT NULL;
CREATE INDEX ix_parties_contrary ON lawsuit_parties (tenant_id, customer_id)
  WHERE pole = 'CONTRARIA';
```
Migration `072_report_indexes.py`.

## 5. Contratos de API

```
GET /api/v1/reports/{report_key}
  ?from=&to=&user_id=&action_group_id=&cursor=&limit=&sort=&order=
POST /api/v1/reports/{report_key}/export → {format}
```

`report_key`: `productivity` · `delayed_tasks` · `access_logs` · `new_customers` ·
`new_lawsuits` · `won_lawsuits` · `lost_lawsuits` · `hearings` · `contrary_parties`

Colunas por relatório:
- **productivity:** responsável, cliente, tarefa, pontuação, data compromisso, conclusão
- **delayed_tasks:** responsável, cliente, tarefa, pontuação, data compromisso, tempo de atraso
- **access_logs:** colaborador, data, IP, primeiro login, último login
- **new_customers:** nome, contato, cidade/UF, origem, data
- **new_lawsuits:** partes, tipo de ação, número, responsável, data
- **won/lost_lawsuits:** partes, tipo, número, honorários, fechamento, tempo total
- **hearings:** data, hora, tipo, processo, partes, local, advogado
- **contrary_parties:** nome, documento, cidade, nº de processos

## 6. Front-end

**Reutiliza:** `DataTable`, `FilterBar`, `EmptyState`, `ListPageLayout` (de 030)
**Cria:** `ReportSelect`, `ReportPage` (genérica, dirigida por metadados), `ReportTotalsRow`
**Rota:** `/reports?report=`

## 7. Regras de negócio

1. Uma **página genérica** serve os 9 relatórios — cada um é definido por metadados (colunas,
   filtros, query). Nove telas escritas à mão seria falha de design.
2. Todos são **tempo real** (sem view materializada) — é lista filtrada, não agregação pesada.
3. Filtros comuns: período, responsável, grupo de ação. Cada relatório pode declarar filtros extras.
4. `productivity` e `delayed_tasks` mostram a soma de pontos no rodapé.
5. `access_logs` só aparece se `track_access_logs` estiver ligado (012); senão, estado vazio explicando.
6. `won_lawsuits` / `lost_lawsuits` filtram por `outcome`, no período de `closure_date`.
7. Tempo total do processo = `closure_date` − `created_at`, em dias.
8. `hearings` filtra tarefas do tipo sistêmico "Pauta de audiências" com data futura.
9. `contrary_parties` conta processos por parte com `pole = CONTRARIA`.
10. Export respeita filtros; teto de 50.000 linhas.
11. Todos exigem ADMINISTRADOR, exceto `productivity`, que o Colaborador vê com os próprios dados.
12. Paginação keyset.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | **os 9 relatórios com seed determinístico** (parametrizado) | ~1,4 s |
| integração | filtros comuns em todos | ~0,5 s |
| integração | rodapé soma pontos | ~0,3 s |
| integração | `access_logs` desligado → estado vazio | ~0,3 s |
| integração | ganhos e perdidos por `closure_date` | ~0,4 s |
| integração | tempo total em dias | ~0,2 s |
| integração | pauta só com data futura | ~0,3 s |
| integração | contrárias conta processos | ~0,3 s |
| integração | Colaborador só vê a própria produtividade | ~0,3 s |
| integração | export respeita filtros | ~0,4 s |
| frontend | página genérica renderiza 3 relatórios distintos | ~0,6 s |

**Total:** ~5,0 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Uma página genérica, não nove · Commit `feat(072): relatórios tabulares`
