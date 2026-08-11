# 054 — Financeiro: plano de contas

**Fase:** 5 · **Tipo:** feature · **Orçamento:** +3 s
**Depende de:** 011 · **Status:** ✅ concluída

---

## 1. Objetivo

A estrutura contábil do escritório: grupos DRE, categorias de receita e despesa, centros de
custo. Define como o dinheiro é classificado e, consequentemente, como o DRE fecha (062).

## 2. Escopo

- Tabela `dre_groups` com os 10 grupos (seed fixo)
- Tabela `financial_categories` com as 61 padrão
- Tabela `cost_centers`
- CRUD + transferência antes de excluir
- Tela `Configurações > Financeiro`

## 3. Fora de escopo

- Contas e cartões → 055 · Lançamentos → 056 · DRE → 062

## 4. Modelo de dados

```sql
CREATE TYPE entry_type AS ENUM ('RECEITA','DESPESA');

CREATE TABLE dre_groups (          -- global, imutável
  id SMALLINT PRIMARY KEY,         -- 0..9
  name TEXT NOT NULL UNIQUE,
  nature entry_type NOT NULL
);

CREATE TABLE financial_categories (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  dre_group_id SMALLINT NOT NULL REFERENCES dre_groups(id),
  name TEXT NOT NULL,
  type entry_type NOT NULL,
  is_default BOOLEAN NOT NULL DEFAULT false,   -- veio do seed
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);
CREATE INDEX ix_fin_cat_type ON financial_categories (tenant_id, type) WHERE is_active;

CREATE TABLE cost_centers (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  name TEXT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, name)
);
```
RLS em categorias e centros. Migration `054_chart_of_accounts.py`.

**Seed dos 10 grupos DRE:**
`0` Deduções da receita bruta (DESPESA) · `1` Receitas (RECEITA) · `2` Folha de pagamento ·
`3` Encargos sociais · `4` Tributos · `5` Despesas fixas · `6` Despesas variáveis ·
`7` Despesas bancárias · `8` Marketing e comercial · `9` Distribuição de lucros (todas DESPESA)

**Seed de 61 categorias:** 14 de receita e 47 de despesa, conforme
`docs/ADVBOX-ESPECIFICACAO-COMPLETA.md` §3.9. Centro de custo padrão: `GERAL`.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/api/v1/dre-groups` | financial ≥ READ_ONLY |
| GET | `/api/v1/financial-categories?type=&group=&status=&q=` | financial ≥ READ_ONLY |
| POST/PUT/DELETE | `/api/v1/financial-categories[/{id}]` | financial = FULL **e** GESTOR |
| GET | `/api/v1/cost-centers?status=&q=` | financial ≥ READ_ONLY |
| POST/PUT/DELETE | `/api/v1/cost-centers[/{id}]` | financial = FULL |
| POST | `/api/v1/financial-categories/transfer` · `/cost-centers/transfer` | financial = FULL |

## 6. Front-end

**Reutiliza:** `DataTable`, `FilterBar`, `FormModal`, `TransferBeforeDeleteDialog`
**Cria:** `CategoryForm` (grupo filtra por natureza), `DreGroupBadge`
**Rota:** `/settings/financial` com 3 abas

## 7. Regras de negócio

1. Os 10 grupos DRE são **imutáveis** — sem POST, PUT ou DELETE.
2. Categoria de RECEITA só aceita grupo de natureza RECEITA (grupo `1`). Despesa, os demais.
   Exceções semeadas (`5. PAGAMENTO DE FATURA` e `6. REEMBOLSO` como receita) existem no ADVBOX
   real e são permitidas — a validação é por `type` da categoria, não pela natureza do grupo.
3. Categoria `is_default = true` não pode ser excluída, só inativada.
4. Excluir categoria ou centro em uso exige transferência.
5. Nome único por tenant, sem acento na comparação.
6. Escrita exige `financial_access = FULL`; categorias exigem também GESTOR.
7. Leitura exige `financial_access ≥ READ_ONLY` — quem tem `NONE` recebe 403.
8. Centro de custo `GERAL` é semeado e não pode ser excluído.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | grupos DRE são somente leitura (POST → 405) | ~0,2 s |
| integração | CRUD de categorias e centros | ~0,5 s |
| integração | categoria padrão não é excluível | ~0,2 s |
| integração | excluir em uso → 409; transferência funciona | ~0,4 s |
| integração | `financial_access = NONE` → 403 na leitura | ~0,2 s |
| integração | `READ_ONLY` lê mas não escreve | ~0,3 s |
| integração | Colaborador com FULL cria centro de custo | ~0,2 s |
| integração | Colaborador com FULL **não** cria categoria (exige GESTOR) | ~0,2 s |
| integração | RLS entre tenants | ~0,3 s |
| unit | seed: 10 grupos, 61 categorias, 1 centro | ~0,2 s |

**Total:** ~2,7 s

## 9. Descobertas

- **O seed das 61 categorias/centro `GERAL` só atinge tenants que já existiam no
  momento da migration.** Mesma limitação já documentada em 011/012/014/015 — não há
  spec de provisionamento de tenant ainda, então um tenant novo nasce sem plano de
  contas até alguém rodar a migration de novo (o que não recria nada por causa do
  `ON CONFLICT DO NOTHING`) ou cadastrar na mão. Testado via unit test na migration
  (estrutura do seed) + backfill direto por SQL nos testes de integração que precisam
  de uma linha `is_default` de verdade.
- **`cost_centers` ganhou a coluna `is_default`, que não está no esboço SQL da spec.**
  Sem ela, a regra 8 ("centro GERAL nunca é excluível") só teria como se apoiar em
  comparar `name == 'GERAL'` — frágil a rename. Mesmo padrão já usado em
  `financial_categories.is_default` (que a spec JÁ desenhava).
- **Regra 2 ("validação é por type da categoria, não pela natureza do grupo") virou
  NENHUMA validação cruzada no backend.** `dre_group_id` só precisa existir (422 se
  não); `type` é independente. As 2 exceções reais do ADVBOX (`PAGAMENTO DE FATURA` e
  `REEMBOLSO DE CUSTO POR CLIENTES`, tipo RECEITA em grupos de natureza DESPESA) só
  são possíveis porque não há esse cross-check. No frontend, `CategoryForm` filtra o
  `<select>` de grupo pela natureza do `type` escolhido — só um guia de UX — e sempre
  mantém visível o grupo já selecionado mesmo que não bata com o tipo (senão editar
  uma das 2 exceções faria o valor sumir da lista).
- **Transferência de categorias/centros segue o mesmo no-op documentado de
  `customer_origins` (016)/`stages` (015)/`action_groups` (014).** Nada referencia
  `financial_categories`/`cost_centers` ainda — lançamentos chegam na spec 056 — então
  a validação (`from_id`/`to_id` existem e são distintos) é real, mas a reatribuição
  em si devolve sempre `0`.
- **Primeira vez que `require_financial` (definido desde a spec 011) é usado de
  verdade num router.** Dupla dimensão de permissão (regra 6) implementada como 2
  `Depends` separados na MESMA rota — `require_role(GESTOR)` e
  `require_financial(FULL)` para categorias; centros de custo só o segundo. Cada um
  levanta 403 independente; o teste de cobertura de permissão (`test_permission_
  coverage.py`) já aceita múltiplas dependências de permissão na mesma rota sem
  mudança.
- **`TransferBeforeDeleteDialog` citado no §6 mas não ligado na UI.** Mesmo precedente
  de `StagesListPage` (spec 015): sem uma contagem real de "em uso" pra decidir quando
  mostrar o diálogo (nada referencia essas tabelas ainda), a tela usa só
  `ConfirmDialog` — o botão "Excluir" nem aparece pra linhas `is_default`, guiando o
  usuário a inativar em vez de tentar excluir.
- **UI verificada manualmente num browser real (Playwright), não só pelos testes.**
  As 3 abas renderizando dados reais via API, formulário de categoria com o filtro de
  grupo por tipo funcionando (RECEITA só mostra "Receitas" no select), criação
  ponta a ponta confirmada por screenshot (nome → tipo → grupo → salvar → aparece na
  tabela com o badge correto).

## 10. Definição de pronto

- [x] Escopo implementado, nada além (contas/cartões ficam pra 055; lançamentos pra
      056; DRE pra 062 — nenhuma das três tocada aqui)
- [x] Todas as regras de negócio com teste (10 testes de integração cobrindo as 8
      regras: grupos imutáveis, CRUD, categoria/centro padrão não excluível mas
      editável, transferência real+no-op, `financial_access=NONE`→403,
      `READ_ONLY` lê sem escrever, dupla dimensão de permissão nas duas direções —
      Colaborador+FULL cria centro mas não categoria — e isolamento por tenant)
- [x] Teste de isolamento por tenant — `financial_categories`/`cost_centers` são
      tabelas novas com RLS via `enable_rls_statements` (migration 054);
      `test_tenant_a_nao_ve_categoria_nem_centro_de_tenant_b` prova leitura E escrita
      (PUT por id de outro tenant → 404)
- [x] `make test` verde e wall-clock < 300 s (222 s — 779 backend, 147 frontend, 9 e2e;
      nenhuma jornada e2e nova, dentro do orçamento de +3 s previsto no §8)
- [x] `make lint` verde (ruff, black, mypy, eslint, tsc, prettier)
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário
- [x] `ROADMAP.md` atualizado para ✅
- [x] Dupla dimensão de permissão testada (regra 6): financial_access × role, nas duas
      direções (READ_ONLY não escreve mesmo sendo GESTOR; COLABORADOR com FULL cria
      centro mas não categoria, que também exige GESTOR)
- [x] Componentes reutilizáveis: `DataTable`/`FilterBar`/`FormModal`/`useCrudResource`
      reaproveitados sem duplicar (3 telas de cadastro, zero código de tabela/filtro/
      modal escrito do zero); `CategoryForm`/`DreGroupBadge` novos, do jeito que o §6
      previa
- [x] Commit `feat(054): Financeiro — plano de contas`
