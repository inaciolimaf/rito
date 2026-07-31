# 027 — Processos: listagem, visões e filtros

**Fase:** 2 · **Tipo:** feature · **Orçamento:** +7 s
**Depende de:** 026 · **Status:** ⬜ pendente

---

## 1. Objetivo

A tela de trabalho do gestor. 12 visões rápidas pré-definidas mais um conjunto amplo de filtros
combináveis — é aqui que se descobre processo parado e prazo em risco.

## 2. Escopo

- Listagem com `DataTable` + `FilterBar`
- 12 visões rápidas em seletor único
- Filtros avançados combináveis
- Export xlsx/pdf
- Coluna de último andamento

## 3. Fora de escopo

- Dashboard → 028 · Kanban → 051 · Busca global → 096

## 4. Modelo de dados

Nenhuma tabela nova. Índices e coluna materializada para performance:

```sql
ALTER TABLE lawsuits ADD COLUMN last_movement_at TIMESTAMPTZ;
CREATE INDEX ix_lawsuits_last_movement ON lawsuits (tenant_id, last_movement_at DESC NULLS LAST);
CREATE INDEX ix_lawsuits_created       ON lawsuits (tenant_id, created_at DESC);
```
`last_movement_at` é atualizada por trigger ao inserir em `lawsuit_movements` — calcular
"parado há +90 dias" com subquery em cada listagem não escala.

Migration `027_lawsuits_list_indexes.py`.

## 5. Contratos de API

```
GET /api/v1/lawsuits
  ?view=<uma das 12>
  &q=&customer_id=&identification=&process_number=&protocol_number=&folder=&notes=
  &action_group_id=&lawsuit_type_id=&step_id=&stage_id=&court_id=&court_system_id=
  &user_id=&contingency=&origin_id=&customer_type=
  &created_from=&created_to=&process_date_from=&process_date_to=
  &closure_from=&closure_to=&transit_from=&transit_to=&archived_from=&archived_to=
  &archived=&cursor=&limit=&sort=&order=
```

**As 12 visões (`view`):** `all` · `active` · `moved_30d` · `moved_7d` · `moved_today` ·
`never_captured` · `idle_30d` · `idle_45d` · `idle_90d` · `closed_this_month` ·
`filed_this_month` · `archived_this_month`

| Método | Rota |
|---|---|
| POST | `/api/v1/lawsuits/export` |

## 6. Front-end

**Reutiliza:** `DataTable`, `FilterBar`, `EmptyState`
**Cria:** `LawsuitListPage`, `QuickViewSelect`, `LastMovementCell`
**Rota:** `/lawsuits`

Colunas: Partes · Tipo de ação · Número do processo · Data cadastro · Último andamento · Data andamento

## 7. Regras de negócio

1. Visão e filtros são combináveis — visão é atalho, não exclusividade.
2. `active` = não arquivado e sem `archived_date`.
3. `idle_Nd` = `last_movement_at` mais antigo que N dias **ou** nulo.
4. `never_captured` = `last_movement_at IS NULL`.
5. Busca textual (`q`) varre nome de parte, número, protocolo e pasta.
6. `identification` casa CPF/CNPJ de qualquer parte do processo.
7. Filtros de data funcionam como intervalo; um lado só é aceito.
8. Filtros combinam com AND; multivalorados combinam com OR entre si.
9. Estado inteiro na URL.
10. Export respeita filtros; teto de 50.000 linhas.
11. Paginação keyset.
12. Coluna de partes mostra as 2 primeiras + contador.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | cada uma das 12 visões (tabela parametrizada) | ~1,2 s |
| integração | visão + filtro combinam | ~0,3 s |
| integração | busca textual nas 4 fontes | ~0,4 s |
| integração | `identification` casa parte contrária | ~0,3 s |
| integração | intervalo com um lado só | ~0,3 s |
| integração | multivalorado usa OR interno | ~0,3 s |
| integração | trigger mantém `last_movement_at` | ~0,4 s |
| integração | **budget: listagem ≤ 3 statements** | ~0,4 s |
| integração | keyset estável | ~0,4 s |
| frontend | seletor de visão atualiza a URL | ~0,4 s |
| frontend | coluna de partes trunca com contador | ~0,3 s |
| e2e | **jornada 4/25:** criar processo → filtrar por visão → abrir timeline | ~5 s |

**Total:** ~9,7 s

> Acima do orçamento declarado de 7 s. Reduza movendo a jornada e2e para integração se o
> wall-clock global apertar — a spec 030 vai cobrar isso.

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · 12 visões testadas · Commit `feat(027): processos — listagem e filtros`
