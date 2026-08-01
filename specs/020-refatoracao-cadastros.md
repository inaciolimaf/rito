# 020 — 🔧 REFATORAÇÃO — Cadastros

**Fase:** 1 · **Tipo:** refatoração · **Orçamento:** reduzir
**Depende de:** 011–019 · **Status:** ✅ concluída

---

## 1. Objetivo

Primeira refatoração sobre código de domínio. Aqui aparece o padrão que vai se repetir 70 vezes:
entidade + CRUD + listagem + filtro + transferência antes de excluir. Se esse padrão não for
extraído agora, ele será copiado e colado dezenas de vezes.

> Refatoração não muda comportamento. Testes de 011–019 passam **sem edição**.

## 2. Alvo principal: extrair o padrão CRUD

Cinco entidades já repetiram a mesma estrutura (grupos, tipos de ação, etapas, origens, times):

- [x] ~~`CrudRouter` genérico~~ — **rejeitado deliberadamente**, ver seção 9. No lugar:
      `app/core/http.get_or_404`/`parse_active_status` (mecânico, aplicado a **7** routers —
      as 5 taxonomias + `customers` + `users`).
- [x] `TransferableMixin` — virou `app/core/transfer.validated_transfer` +
      `app/core/exceptions.InvalidTransferError` (a validação é idêntica nos 3 domínios que
      têm transferência; a reatribuição em si continua específica de cada um).
- [x] `ActivatableMixin` — virou uma função (`parse_active_status`), não uma classe, ver seção 9.
- [x] `useCrudResource` no frontend — `components/domain/useCrudResource.ts`, aplicado às 5
      páginas de listagem simples.
- [x] ~~`SettingsListPage` genérica~~ — **rejeitada deliberadamente**, ver seção 9.

## 3. Checklist

### Cobertura
- [x] Toda regra numerada das specs 011–019 tem teste — nenhuma lacuna nova encontrada (as
      lacunas já documentadas — customer_origins.transfer/delete sem lógica real, busca sem
      unaccent — são comportamento, não cobertura; ver docs/DIVIDA-TECNICA.md #12/#13)
- [x] Caminhos de erro cobertos, não só o feliz — confirmado nos 299 testes pré-existentes
- [x] Todas as 8 tabelas novas (011–019) com teste de isolamento entre tenants — confirmado
      (accounts, users, squads/squad_members, action_groups/lawsuit_types, steps/stages,
      customer_origins, customers)
- [x] Constraints do banco testadas (não só a validação da aplicação) — `uq_*` únicos,
      `ck_stages_stagnant_days`, FKs, tudo com teste de integração desde a spec original

### SOLID
- [x] Nenhum router com query — confirmado nos 7 routers tocados
- [x] Nenhum service importando `httpx` direto (ViaCEP atrás de `AddressLookup`) — confirmado
- [x] Validadores de CPF/CNPJ/telefone em módulo próprio (`app/core/br_documents.py`), sem
      dependência de framework — confirmado
- [x] Repositórios herdando de `BaseRepository`, sem SQL solto — confirmado nos 5 domínios

### Duplicação
- [x] Padrão CRUD extraído (item 2) — na medida do que é seguro (ver seção 9)
- [x] Validação duplicada entre Pydantic e Zod com fonte única — já era o padrão desde a 011
      (máscara/tamanho no cliente, regra real só no backend); nada novo a extrair
- [x] Máscaras de formatação em um único lugar — `CpfCnpjField`/`PhoneField`/`PostalCodeField`
      (spec 018) já são a fonte única, reusadas por `customers`
- [x] `TransferBeforeDeleteDialog` usado pelo único consumidor real (`ActionGroupsListPage`) —
      `customer_origins`/`stages` ainda não têm "em uso" real para acionar o diálogo (ver
      docs/DIVIDA-TECNICA.md #13), então não foi forçado nas outras 2 telas
- [x] `InvalidTransferError` deduplicado (3 classes idênticas → 1 em `app/core/exceptions.py`)
- [x] `get_or_404`/`parse_active_status` deduplicados (padrão idêntico em 7 routers)

### Banco
- [x] Toda FK com índice — auditado nas 5 tabelas (squads, squad_members, action_groups,
      lawsuit_types, stages, customer_origins): todas já têm índice em toda FK (`ix_*_tenant`
      + índice específico por FK não-tenant), nenhuma lacuna encontrada
- [x] Índices de 019 realmente usados — estrutura das queries confere com as expressões
      indexadas (`EXTRACT(MONTH/DAY FROM birthdate)`, `(tenant_id, origin_id) WHERE NOT
      is_archived`, etc.); `EXPLAIN` com volume real não foi possível — bancos de dev/teste
      estão vazios, o planner sempre escolhe seq scan em tabela pequena independente do
      índice existir (comportamento correto do Postgres, não uma lacuna)
- [x] Nenhuma query de listagem acima de 5 statements (N+1) — auditado: `squads` e
      `action_groups` já usam contagem/membros em lote (`get_members_for_squads`,
      `count_lawsuit_types`), nenhuma lacuna encontrada
- [x] Seeds idempotentes e rápidos — `INSERT ... ON CONFLICT` em todas as migrations de seed
      (016, 015), confirmado

### Tipos
- [x] `mypy --strict` e `tsc --noEmit` verdes
- [x] Zero `Any` / `as any` sem justificativa — nenhum novo introduzido nesta spec

### Performance dos testes
- [x] Wall-clock **< 90 s** — medido: ver seção 10
- [x] Seeds de teste em escopo de sessão — inalterado (template DB, spec 009)
- [x] E2E com no máximo 3 jornadas até aqui — confirmado (3/25, inalterado nesta spec)

## 4. Entregáveis

1. [x] Padrão CRUD extraído (`get_or_404`, `parse_active_status`, `validated_transfer` +
       `InvalidTransferError` no backend; `useCrudResource` no frontend) e as 5 entidades
       (+ `customers` e `users` para os 2 primeiros) migradas para ele
2. [x] `docs/DECISOES.md` atualizado — seção "Refatoração de cadastros (spec 020)"
3. [x] Este arquivo documenta `get_or_404`/`parse_active_status`/`validated_transfer`/
       `useCrudResource` — decidiu-se não adicionar uma seção nova em `CLAUDE.md` porque
       nenhum deles é uma convenção de arquitetura nova (são helpers pontuais, não um padrão
       que toda spec futura precise conhecer de cor); ficam documentados aqui e em
       `docs/DECISOES.md`
4. [x] `test-timing.json` atualizado
5. [x] Dívidas em `docs/DIVIDA-TECNICA.md` — item #2 resolvido, itens #11/#12/#13 novos

## 5. Definição de pronto

- [x] Testes de 011–019 passam sem edição — **299 testes pré-existentes, zero arquivo de
      teste editado**; 9 testes novos cobrem os helpers extraídos (`test_core_http.py`,
      `test_core_transfer.py`) — 308 no total
- [x] Wall-clock < 90 s — ver seção 10
- [x] Uma taxonomia nova custa < 50 linhas — **não demonstrável como escrito**; ver seção 9
      para a correção honesta desta meta

## 9. Descobertas

**Por que não existe um `CrudRouter` genérico nem uma `SettingsListPage` genérica.** As 5
taxonomias simples têm o mesmo esqueleto de validação/erro (get-or-404, conflito de nome →
409, ids inválidos → 422), mas resposta e regra de negócio genuinamente diferentes por
domínio: `squads` junta membros (`get_members_for_squads`), `action_groups` conta
`lawsuit_types` vinculados, `lawsuit_types` injeta o nome do grupo, `stages` calcula
`position`/pertence a uma fase. Um `CrudRouter` único que gerasse as 4 rotas a partir de um
schema teria que aceitar tantos hooks de personalização por variação (mapeamento de resposta,
query params extras, exceções específicas) que o resultado seria mais código, não menos —
abstração prematura, o oposto do que "regra dos 3 usos" pede (extrair o que É idêntico, não
forçar o que não é). O mesmo raciocínio vale para `SettingsListPage`: as 5 páginas têm
colunas, filtros e ações de linha genuinamente diferentes; uma versão "genérica" reexporia
praticamente toda a API do `DataTable`/`FilterBar`/`FormModal` por fora, sem reduzir código de
verdade. Extraído em vez disso: `get_or_404`/`parse_active_status` (a parte que É idêntica,
mecânica, aplicada a **7** routers — as 5 taxonomias + `customers` + `users`, todos dentro do
escopo 011–019) e `validated_transfer`/`InvalidTransferError` (a validação de "transferir
antes de excluir", idêntica nos 3 domínios que a têm). No frontend, `useCrudResource` extrai
o ciclo de vida de modal/edição/erro/exclusão pendente das 5 páginas, deixando o formato do
payload (que varia por entidade) como callback definido pela própria feature.

**A meta "uma taxonomia nova custa < 50 linhas" da seção 5 original não é alcançável como
estava escrita, e isso é consequência direta de ter rejeitado o `CrudRouter` genérico.** Um
router com 4-5 endpoints reais (list/create/update/delete[/transfer]), mesmo já usando
`get_or_404`/`parse_active_status`, fica em ~100 linhas (medido em `customer_origins/router.py`
pós-refatoração: 103 linhas) — porque cada endpoint ainda declara sua própria assinatura,
mapeamento de resposta e captura de exceção, que é justamente a parte que um `CrudRouter"
apagaria e que foi deliberadamente preservada por ser heterogênea demais para generalizar com
segurança. A meta original presumia a existência do `CrudRouter` que não foi construído. Uma
taxonomia nova de verdade (model + schema + repository + service + router + migration +
página de frontend + cliente de API) continua custando a ordem de 150-250 linhas end-to-end —
a maior parte é forma de negócio irredutível (colunas do schema, campos do formulário), não
duplicação. O que a spec 020 reduziu de fato: ~3-6 linhas de boilerplate por endpoint (7
routers) e ~25-30 linhas de estado/handlers por página de listagem (5 páginas) — real, mas
não o "< 50 linhas" prometido.

**Achados de pente-fino documentados, não corrigidos (mudariam comportamento).** Três itens
novos em `docs/DIVIDA-TECNICA.md`:
- **#11** `squads` (spec 013) é a única das 5 taxonomias com nome único sensível a
  maiúsculas/acento — as outras 4 usam `immutable_unaccent(lower(name))`, convenção só
  introduzida na spec 014 (posterior a squads).
- **#12** as 5 listagens buscam texto com `ilike` puro (não ignora acento), diferente de
  `customers` (spec 019), que unaccenta os dois lados da comparação — mesmo a checagem de
  duplicidade (`get_by_name`) dessas 5 já sendo accent-insensitive.
- **#13** `CustomerOriginService.transfer`/`delete` continuam sem lógica real
  (`transfer` sempre retorna `0`, `delete` sem guarda de "em uso") apesar de
  `customers.origin_id` existir desde a spec 017 — o teste
  `test_excluir_nao_bloqueia_ainda` documenta e prova o no-op atual.

Nenhum dos três foi corrigido porque fixá-los muda comportamento observável (mais nomes
colidem, mais buscas encontram resultado, exclusões passam a ser bloqueadas) — proibido em
spec de refatoração (CLAUDE.md §8). Cabe a uma spec de feature dedicada.

**Débito #2 (`docs/DIVIDA-TECNICA.md`) resolvido.** `@vitest/coverage-v8@3.2.7` instalado
(pinado na mesma major do `vitest` já usado — a v4 do pacote quebraria o projeto). Script
`npm run test:coverage`, opt-in (não entra em `npm run test`/`make test` por padrão, mesmo
padrão do `pytest --cov` do backend). Overhead medido: ~4-5 s sobre a suíte sem cobertura.
Estado inicial: 63% de statements/lines, 74% de branches, 57% de functions.

**Nenhuma lacuna nova de índice de FK ou N+1 encontrada** nas 5 tabelas + `customers` — a
disciplina das specs 013-019 já cobriu isso desde o início (índice em toda FK, contagem/
membros em lote em vez de por linha).

## 10. Medição

- Backend: **308 testes** (299 pré-existentes, inalterados + 9 novos para
  `get_or_404`/`parse_active_status`/`validated_transfer`) em ~25-27 s
- Frontend: **62 testes** (inalterados) em ~19-23 s (com cobertura: +4-5 s)
- E2E: **4 jornadas** (3/25 pré-existentes + a nova de contatos da spec 019, inalterada) em
  ~11-33 s
- `make test` (wall-clock medido, 3 suítes concorrentes): **48 s** — dentro do orçamento de
  90 s desta spec e do teto geral de 120 s
- `ruff check .` / `black --check .` / `mypy .` (backend): limpos
- `eslint . && tsc -b --noEmit && prettier --check .` (frontend): limpo (só os 3 warnings
  pré-existentes de `react-refresh/only-export-components`, não relacionados a esta spec)
- Verificação manual em navegador: CRUD de origem de pessoas (criar → editar → excluir) e o
  fluxo mais arriscado desta refatoração — grupos de ação com transferência obrigatória antes
  de excluir (`ActionGroupsListPage`, que tem estado extra de diálogo de transferência sobre o
  `useCrudResource` base) — via script Playwright ad-hoc não commitado
