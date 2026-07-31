# 019 — Contatos: listagem e dashboard

**Fase:** 1 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 018, 007 · **Status:** ⬜ pendente

---

## 1. Objetivo

A primeira tela completa do sistema — e a prova de que o design system da spec 007 funciona.
Listagem com filtros, dashboard analítico e export.

## 2. Escopo

- Listagem com `DataTable` + `FilterBar`
- Dashboard: cards + 3 gráficos (Top Origens, Faixa etária, Top Profissões)
- Aniversariantes do dia e do mês
- Export xlsx/pdf respeitando os filtros
- Endpoint de agregação

## 3. Fora de escopo

- Análise da carteira por IA → 089
- Relatório de partes contrárias → 072

## 4. Modelo de dados

Nenhuma tabela nova. Índices para as agregações:

```sql
CREATE INDEX ix_customers_origin      ON customers (tenant_id, origin_id) WHERE NOT is_archived;
CREATE INDEX ix_customers_birthdate   ON customers (tenant_id, (EXTRACT(MONTH FROM birthdate)), (EXTRACT(DAY FROM birthdate)));
CREATE INDEX ix_customers_created     ON customers (tenant_id, created_at DESC);
CREATE INDEX ix_customers_name_trgm   ON customers USING gin (name gin_trgm_ops);
CREATE INDEX ix_customers_occupation  ON customers (tenant_id, occupation) WHERE occupation IS NOT NULL;
```
Migration `019_customers_indexes.py`.

## 5. Contratos de API

| Método | Rota |
|---|---|
| GET | `/api/v1/customers?q=&type=&state=&city=&origin_id=&created_from=&created_to=&has_active_lawsuit=&birthdays=&archived=&cursor=&limit=&sort=&order=` |
| GET | `/api/v1/customers/stats` |
| GET | `/api/v1/customers/birthdays?scope=day\|month` |
| POST | `/api/v1/customers/export` → `{format: "xlsx"\|"pdf", filters: {...}}` |

`stats` retorna: `total`, `variation_vs_last_month`, `with_active_lawsuit`,
`without_active_lawsuit`, `top_origins[]`, `age_ranges[]`, `top_occupations[]`.

## 6. Front-end

**Reutiliza:** `DataTable`, `FilterBar`, `StatCard`, `EmptyState`, `FormModal`
**Cria:** `CustomerListPage`, `CustomerStatsPanel`, `BirthdayBadge`, `DonutChart`, `BarChart`
**Rota:** `/customers`

Colunas: Nome do cliente · Celular (link WhatsApp) · Cidade · Data do cadastro
Filtros: busca, tipo (Clientes / Partes contrárias / Com processo ativo / Sem processo ativo /
Aniversariantes do dia / do mês), estado, cidade, origem, período de cadastro, arquivados

## 7. Regras de negócio

1. Busca por nome é parcial, case-insensitive e **sem acento**; por CPF/CNPJ é exata.
2. Filtros combinam com **AND**.
3. Filtros vivem na URL — o link é compartilhável.
4. Faixas etárias: 0–17, 18–24, 25–34, 35–44, 45–54, 55–64, 65+. Sem nascimento → "Não informado".
5. Top Origens e Top Profissões trazem os 10 primeiros e agrupam o resto em "Outros".
6. Aniversariantes ignoram o ano (compara mês e dia).
7. Export respeita os filtros ativos, não a página visível; teto de 50.000 linhas.
8. Celular vira link `https://wa.me/55<DDD><numero>`.
9. Arquivados ficam ocultos por padrão.
10. Paginação **keyset**, nunca offset.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | busca parcial ignora acento | ~0,3 s |
| integração | filtros combinam com AND | ~0,4 s |
| integração | paginação keyset é estável com inserção concorrente | ~0,4 s |
| integração | stats com seed determinístico | ~0,4 s |
| integração | faixas etárias, incluindo "não informado" | ~0,3 s |
| integração | aniversariantes do dia e do mês | ~0,3 s |
| integração | export respeita filtros | ~0,4 s |
| integração | arquivados ocultos por padrão | ~0,2 s |
| frontend | filtros refletem na URL e voltam | ~0,5 s |
| frontend | estado vazio com ação de criar | ~0,3 s |
| frontend | link de WhatsApp bem formado | ~0,2 s |
| e2e | **jornada 3/25:** criar contato → filtrar → editar → arquivar | ~5 s |

**Total:** ~8,7 s

## 9. Descobertas

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Nenhum componente de tabela ou filtro escrito à mão · Commit `feat(019): contatos — listagem e dashboard`
