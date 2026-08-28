# 019 — Contatos: listagem e dashboard

**Fase:** 1 · **Tipo:** feature · **Orçamento:** +6 s
**Depende de:** 018, 007 · **Status:** ✅ concluída

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

- **"Clientes vs Partes contrárias" e "com/sem processo ativo" adiados.** Ambos dependem de
  `lawsuits`/`lawsuit_customer` (N:N com flag de parte contrária, ADVBOX §3.5), que só chega na
  spec 022 — mesmo padrão de stub das specs 014/015/016/018: `has_active_lawsuit=true` sempre
  retorna vazio, `false`/omitido é no-op, e `with_active_lawsuit`/`without_active_lawsuit` em
  `/stats` ficam fixos em `0`/`total`. O filtro `type` da listagem foi reinterpretado como o
  campo PF/PJ já existente desde a spec 017, não o conceito combinado do ADVBOX.
- **Dependências novas:** `openpyxl` + `fpdf2` (export xlsx/pdf) e `types-openpyxl` (stub para
  mypy). Sem lib de gráfico — `DonutChart`/`BarChart` são SVG artesanal em
  `components/domain/`, dado que só há 2 tipos simples (minimalismo do CLAUDE.md).
- **`lib/api.ts`** ganhou `apiRequestBlob`, compartilhando o `fetchWithAuth` interno com
  `apiRequest` (mesma lógica de retry/refresh de token, sem duplicar) — necessário para os
  downloads binários de export.
- **`CustomersPage.tsx`** (spec 017, tela single-record) foi deletada — `CustomerListPage.tsx`
  a supersede por completo na rota `/customers`, preservando o upload de foto embutido no
  `FormModal` de edição.
- **Lacuna de provisionamento exposta pela jornada e2e nova:** a migration 016 só semeia as 8
  origens padrão para tenants que já existiam no momento em que ela rodou (limitação já
  documentada ali). O tenant e2e nasce depois, via `scripts/seed_e2e.py`, e ficaria sem nenhuma
  origem para o formulário de contato escolher. Corrigido semeando a origem "INDICAÇÃO" em
  `seed_e2e.py` com o mesmo `INSERT ... ON CONFLICT (tenant_id, immutable_unaccent(lower(name)))`
  da migration — não por um id fixo comparado por igualdade exata, que colidia com a variante em
  maiúsculas já existente no banco.
- **`scripts/seed_e2e.py`** também passou o usuário e2e para `GESTOR` (antes ficava em
  `COLABORADOR` implícito, default do model) porque a nova jornada arquiva um contato, e
  arquivar exige `ADMINISTRADOR` ou `GESTOR`. Nenhum teste e2e existente dependia do papel
  anterior.
- **Operacional:** rodar a suíte backend fora do `make test` (ex. `uv run pytest` direto) exige
  passar `--allow-hosts` explicitamente — a env var `PYTEST_ALLOW_HOSTS` só é lida pelo
  Makefile/`run-tests.sh`, o plugin `pytest-socket` não a lê sozinho — e exportar
  `TEST_S3_ENDPOINT_URL` apontando para o MinIO real (senão os testes de upload tentam
  `localhost:9000`).

## 10. Definição de pronto

- [x] Checklist padrão (lint + testes verdes, dentro do orçamento)
- [x] Nenhum componente de tabela ou filtro escrito à mão (`DataTable`, `FilterBar`, `FormModal`,
      `EntityPicker`, `EmptyState`, `ConfirmDialog`, `StatCard` reutilizados; `DonutChart`/
      `BarChart` novos, únicos usos de gráfico no projeto)
- [x] Teste de isolamento de tenant cobre a listagem/stats/export (herdado da RLS de `customers`
      desde a spec 017, exercido pelos filtros novos)
- [x] Jornada e2e 3/25 commitada: criar contato → filtrar → editar → arquivar
- [x] Commit `feat(019): contatos — listagem e dashboard`
