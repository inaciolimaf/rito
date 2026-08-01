# Decisões arquiteturais — specs 001 a 009

> Entregável da spec 010 (refatoração da Fundação). Registra o **porquê** por trás de
> decisões que já moldam o código, para não se perderem em Descobertas espalhadas por
> 9 specs. Atualizar a cada spec de refatoração (020, 030, ...) com o que mudou desde a
> última entrada.

## Multi-tenancy e RLS

- **Duas connection strings, sempre.** `DATABASE_URL` usa a role `rito_app` (sem
  `BYPASSRLS`) — é com ela que a aplicação roda e os testes de isolamento valem de
  verdade. `MIGRATIONS_DATABASE_URL` usa o superusuário do cluster (`rito`) — só para
  `alembic upgrade`, nunca em runtime. Motivo: o usuário do Postgres criado pela imagem
  oficial (`POSTGRES_USER`) é superusuário de cluster, e superusuário **sempre** ignora
  RLS mesmo com `FORCE ROW LEVEL SECURITY`. Rodar testes contra essa role faria os 5
  testes de isolamento da spec 003 passarem por acidente, sem nunca exercitar a política.
- **Tenant nunca sai do WHERE manual.** `set_tenant_context()` seta `app.tenant_id` via
  `SELECT set_config(...)` (não `SET LOCAL` — asyncpg não aceita bind param em `SET`) no
  início de toda sessão (`get_session`). A aplicação nunca filtra tenant explicitamente;
  quem garante isolamento é sempre a política RLS.
- **Header vs. claim.** Endpoints pré-autenticação (login, refresh, logout,
  forgot/reset-password) resolvem o tenant pelo header `X-Tenant-Id` — não há outra forma
  de saber o tenant antes de existir um JWT, já que e-mail só é único *por tenant* e as
  tabelas envolvidas têm RLS `FORCE`. A partir do primeiro JWT válido, todo o resto usa o
  claim do token (`get_current_user`), nunca mais o header — impede um token de um tenant
  ser usado com o header de outro.
- **`enable_rls_statements()` é reaproveitado por toda migration que cria tabela de
  domínio** (`ENABLE`+`FORCE ROW LEVEL SECURITY`, política `tenant_isolation`, índice em
  `tenant_id`) — nenhuma tabela nova declara isso à mão.

## Autenticação e tokens

- **Revogação de família precisa de commit explícito.** Ao detectar reuso de refresh
  token, `AuthService.refresh()` chama `session.commit()` explicitamente antes de levantar
  a exceção — a sessão por request faz rollback em qualquer exceção (`get_session`), o que
  apagaria a revogação de segurança se ela não fosse commitada antes do 401.
  `WeakPasswordError`/`InvalidResetTokenError`/etc. não precisam disso: só mudam estado
  quando têm sucesso.
- **Hash de token ≠ hash de senha.** Refresh/reset tokens usam SHA-256 (`hash_token`), não
  Argon2 — já têm ~256 bits de entropia própria (`secrets.token_urlsafe`), então o custo
  computacional do Argon2 seria puro desperdício; o que se precisa é busca determinística
  por hash, que um salt por hash (Argon2) impediria.
- **Convenção de erro 422 com lista.** `HTTPException(detail={"detail": "...", "errors":
  [...]})` é reconhecida pelo handler RFC 7807 e vira `errors` no corpo da resposta — usada
  pela política de senha (cada critério que falhou) e reutilizável por qualquer spec futura
  que precise de um 422 com lista de erros de negócio (não só de schema do Pydantic).

## RBAC

- **Perfil e acesso financeiro são dimensões ortogonais**, cada um com seu próprio ordinal
  (`_ROLE_ORDER`/`_FINANCIAL_ORDER`). Uma rota GET declara `require_financial(READ_ONLY)`
  (READ_ONLY e FULL passam), uma de escrita declara `require_financial(FULL)` — nenhuma
  lógica especial por método HTTP, só a rota escolhendo o mínimo certo.
- **`UserRole`/`FinancialAccess` moram em `app/domain/users/models.py`**, não em
  `app/core/permissions.py` como a spec 005 sugeria — colocá-los em `permissions.py`
  fecharia um ciclo de import (`users.models` → `permissions` → `auth.deps` →
  `users.models`). `core/permissions.py` importa os enums de `users.models` e contém só a
  matriz/hierarquia/`require_role`/`require_financial`. `core` depender de `domain` aqui é
  uma exceção deliberada — autorização por natureza cruza a fronteira infra/domínio.
- **Capabilities são derivadas, nunca persistidas** (`capabilities_for`) — calculadas a
  partir de `(role, financial_access)` a cada resposta de `/auth/me`.

## Frontend

- **Token de acesso só em memória; refresh token em `localStorage`.** Reload de página
  derruba o access token; o `AuthProvider` usa o refresh token (mais o `tenantId`
  persistido ao lado dele) para reautenticar em silêncio.
- **Refresh disparado por path, não por presença de token.** `apiRequest` mantém uma
  lista de paths pré-autenticação (`/auth/login`, `/auth/refresh`, `/auth/forgot-password`,
  `/auth/reset-password`) que nunca tentam refresh num 401 — todo o resto tenta, **com ou
  sem** access token em memória, porque o caso normal de reautenticação silenciosa (reload
  de página) começa exatamente sem token.
- **Sem lib de tabela/combobox de terceiros.** `DataTable` usa `<table>` nativo,
  `EntityPicker` implementa um combobox mínimo à mão (ARIA `combobox`/`listbox`), `FilterBar`
  usa `<select multiple>` nativo para multiseleção — motivo: design system sem dependência
  extra para o que HTML semântico já resolve.
- **8 tokens semânticos de cor** (`surface`, `primary`, `muted`, `default`, `accent`,
  `danger`, `warning`, `success`), não a paleta padrão do shadcn (`background`/`card`/
  `destructive`) — todo componente novo segue essa convenção; regra de lint própria
  (`eslint-rules/no-literal-tailwind-color.js`) barra cor literal fora dela.

## Pipeline de testes (spec 009)

- **`pytest-socket` com allowlist, não mock de rede por biblioteca** — bloqueia qualquer
  conexão de saída não listada; Postgres/Redis locais ficam liberados via
  `--allow-hosts`, LLM/DJEN/DataJud (specs 041+) sempre via fixture gravada, nunca via
  `--allow-hosts`.
- **Migração do banco de teste é explícita e separada da de dev.** `alembic upgrade head`
  roda com `MIGRATIONS_DATABASE_URL` sobrescrito por `TEST_MIGRATIONS_DATABASE_URL` antes
  do pytest subir — pytest_configure só troca a variável dentro do próprio processo do
  pytest, tarde demais para esse subprocesso externo. Ver Descobertas da 009 para os dois
  bugs reais que a falta dessa separação causou (só apareceram com CI real, dois bancos
  físicos distintos).
- **`run-tests.sh` é sourceable.** O corpo virou uma função `main()`, só invocada
  automaticamente quando o arquivo é executado (`BASH_SOURCE[0] == $0`) — permite ao teste
  do próprio gate (`test_runner.sh`) sourcing + stubs de `run_backend`/`run_frontend`/
  `run_e2e`, sem gastar minutos rodando as suítes de verdade a cada execução do teste.

## Refatoração de cadastros (spec 020)

- **Sem `CrudRouter` genérico de fato.** As 5 taxonomias simples (customer_origins,
  action_groups, lawsuit_types, stages, squads) têm o MESMO esqueleto de validação/erro,
  mas resposta e regras de negócio genuinamente diferentes por domínio (squads junta
  membros, action_groups conta lawsuit_types, lawsuit_types injeta o nome do grupo,
  stages calcula `position`/fase). Um único `CrudRouter` que gerasse as 4 rotas por schema
  teria que aceitar tantos hooks por variação que deixaria de ser mais simples que os
  routers atuais — abstração prematura, contra o espírito de "regra dos 3 usos" (extrair o
  que É igual, não forçar o que não é). Optou-se por 3 helpers cirúrgicos que cobrem
  exatamente a parte idêntica: `app/core/http.get_or_404`/`parse_active_status`
  (mecânico, aplicado a 7 routers: as 5 taxonomias + customers + users) e
  `app/core/transfer.validated_transfer` + `app/core/exceptions.InvalidTransferError`
  (a validação de "transferir antes de excluir", idêntica nos 3 domínios que a têm —
  customer_origins/action_groups+lawsuit_types/stages — mesmo com a reatribuição em si
  sendo específica de cada um).
- **`ActivatableMixin` virou uma função, não uma classe.** `is_active`/filtro por status
  não tem estado compartilhado entre as 5 entidades, só uma transformação idêntica
  (`parse_active_status`) — uma mixin de classe adicionaria uma camada de herança sem
  nenhum ganho sobre uma função pura.
- **`useCrudResource` (frontend) extrai o ciclo de vida, não o payload.** As 5 telas de
  listagem (`CustomerOriginsListPage`, `ActionGroupsListPage`, `LawsuitTypesListPage`,
  `StagesListPage`, `SquadsListPage`) compartilham modal/edição/erro/exclusão pendente +
  submit/delete com invalidação de query — isso virou `components/domain/useCrudResource`.
  O formato do payload de update (ex.: espalhar `is_active` atual, ou o transform de
  `StagesListPage` de form values para o shape da API) continua na FEATURE, passado como
  callback — o hook nunca decide como uma entidade vira payload, só orquestra o resto.
  Fluxos com um passo extra antes de excluir (o diálogo de transferência de
  `ActionGroupsListPage`) usam `setPendingDelete` exposto pelo hook em vez do
  `handleConfirmDelete` padrão.
- **`SettingsListPage` genérica não foi construída.** Mesma razão do `CrudRouter`: as 5
  páginas têm colunas, filtros e ações de linha genuinamente diferentes — uma página
  "genérica" que aceitasse schema+endpoint teria que reexpor praticamente toda a API do
  `DataTable`/`FilterBar`/`FormModal` por fora, sem reduzir código de verdade.
- **Nenhuma correção de comportamento entrou nesta spec**, mesmo onde o pente-fino achou
  bugs reais (busca sem unaccent nas 5 listagens, `squads` com nome sensível a
  maiúsculas/acento diferente das outras 4, `customer_origins.transfer`/`delete` ainda
  sem lógica real apesar de `customers.origin_id` já existir) — CLAUDE.md §8 proíbe
  mudança de comportamento em spec de refatoração; os três viraram itens novos em
  `docs/DIVIDA-TECNICA.md` (#11, #12, #13) para uma spec de feature decidir.
- **Cobertura de frontend instalada** (`@vitest/coverage-v8@3.2.7`, pinado na mesma major
  do `vitest` já usado — a v4 do pacote quebraria o resto). `npm run test:coverage` é
  opt-in, não entra no `make test` padrão — mesmo padrão do `pytest --cov` do backend.

## Ambiente de execução do agente (não é decisão de produto)

- Este sandbox resolve Postgres/Redis via o hostname `dind` (Docker-in-Docker remoto), não
  `localhost` — peculiaridade só deste ambiente de desenvolvimento assistido. `.env.example`
  continua correto com `localhost` para qualquer máquina real; overrides via `TEST_*`/
  `PYTEST_ALLOW_HOSTS`/`DATABASE_URL` explícitos resolvem isso sem contaminar config
  commitada.
