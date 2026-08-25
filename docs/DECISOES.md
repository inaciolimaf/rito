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

## Refatoração de processos (spec 030)

- **`lawsuits.last_movement_at` é coluna materializada, mantida por trigger
  (`set_lawsuit_last_movement`, migration 027).** Motivo: as visões "parado há N dias"
  (027) precisam do máximo de `occurred_at` por processo — uma subquery correlacionada
  por linha de listagem não escala, e ordenar/filtrar por agregado impede índice. A
  trigger roda a cada INSERT em `lawsuit_movements` com `GREATEST(COALESCE(...))` —
  inserção tardia de andamento antigo nunca regride o valor. O UPDATE na trigger toca
  uma linha por INSERT de movimentação (volume baixo por natureza do domínio), sem
  lock de tabela e sem tocar a linha de outros processos. A aplicação NUNCA escreve a
  coluna — quem escreve é só o banco; testes que precisam de andamento antigo usam
  `_seed_tribunal`, não UPDATE direto.
- **Padrão de listagem virou infra em `app/core/listing.py` e `app/core/export.py`
  (alvo 2 da 030).** Contatos (019) e processos (027) tinham repetido: keyset por
  tupla `(sort, id)`, intervalos de data (`datetime.combine(min/max)`), e a montagem
  de workbook/PDF célula a célula. A terceira ocorrência (tarefas, 036) é certa —
  extraído antes dela: `paginate_keyset`, `datetime_range`/`date_range`, `QuickViews`
  (nome → fábrica de predicado, com fallback para o default) e `TableExport`
  (colunas tipadas → xlsx/pdf). No frontend, `useListPage` (URL + query + cursor +
  export) e `ListPageLayout` (cabeçalho + dashboard + FilterBar + conteúdo) — as duas
  telas migradas sem mudar uma linha dos testes existentes.
- **`LawsuitService` dividido por caso de uso:** `PartiesService` (spec 023) e
  `MovementsService` (spec 026) nasceram na 030; `LawsuitService` ficou com CRUD,
  listagem, dashboard e validação CNJ (308 linhas). `list_timeline` permanece como
  delegação fina — a regra "testes de 021–029 passam sem edição" vale também para o
  teste de budget que chama o método direto (spec 026).
- **EXPLAIN das 12 visões: seq scan é o plano CERTO no volume atual.** Rodado no banco
  de dev (dezenas de linhas, 1 tenant): mesmo com `enable_seqscan=off` o planner
  escolhe seq scan — com uma dúzia de páginas de heap, índice é puro overhead. Os
  índices das colunas de predicado existem (`ix_lawsuits_last_movement`,
  `ix_lawsuits_closure`, `ix_lawsuits_archived`, `ix_lawsuits_created`,
  `ix_lawsuits_folder_trgm`) e foram conferidos em `pg_indexes`. Revalidar com volume
  real na spec 098 (performance) — registrado como dívida #14.

## Tarefas e caixa de entrada (spec 040)

- **`app/core/dates.py` é o módulo único de datas (alvo 1).** Puro (sem banco/relógio/
  framework): dias úteis e feriados, ocorrências de recorrência (com os enums
  `RecurrencePeriod`/`RecurrenceWeek` — os valores do PG enum não mudaram, só a casa da
  classe) e aritmética de mês (`month_end`, `next_month_start`, `previous_month_start`,
  `nth_weekday`, `last_weekday`), que estava duplicada em lawsuits/stats e taskscore.
  `posts/recurrence.py` e `workflows/business_days.py` viraram shims de re-export para
  os testes de 034/038, que passam sem edição. **057 (parcelamento) e 086 (prazo
  processual) devem importar daqui.**
- **`PostService` dividido por caso de uso (alvo 2):** `creation.py`
  (CreatePostUseCase — referências, expansão de squad, duplicata, reward_snapshot),
  `completion.py` (CompletePostUseCase — complete/reopen/lida/estrela com o disparo da
  recorrência), `detail.py` (PostDetail + build_detail compartilhado pelos três).
  `PostService` ficou com leitura/edição/flags (~120 linhas). `all_completed` virou
  dado (PostRepository) — a conclusão em massa da inbox não alcança mais membros
  privados de outro service.
- **Caixa de entrada medida com 20.000 linhas (10k pendentes + 10k concluídas do mesmo
  usuário, RLS ativo, melhor de 3, execução isolada):** contadores das 6 seções em 1
  query = **79 ms**; página de seção (20+1, keyset) = **87 ms**; partes + nomes dos
  responsáveis da página em batch = **14 ms**. Tela completa ≈ **180 ms < 200 ms** da
  DoD. EXPLAIN: acesso a `post_users` sempre indexado (o planner prefere sair pelos
  posts + `uq_post_users_post_user` quando o join de `task_types` é barato; o índice
  parcial `ix_post_users_pending` é escolhido na forma "minhas pendentes" sem join).
  O teste automatizado (`test_inbox_perf.py`) usa limiares de 200 ms (≈2,5× o medido)
  para não flakkar sob `-n auto`; o seed é module-scoped por worker e se autodestrói.

## Refatoração das integrações CNJ (spec 050)

- **`SyncRun` unificado, não `SyncJob[T]` genérico.** O esqueleto de DJEN (044) e DataJud
  (047) parece igual de longe (buscar unidades, iterar, isolar falha, atualizar status),
  mas diverge em pontos que importam: DJEN faz *paginação multi-fetch* dentro de uma
  janela de datas por termo; DataJud faz *um fetch por processo*, sem paginação. DJEN
  trata falha como algo que se resolve sozinho (alerta + retry diário — spec 049); DataJud
  trata "não encontrado" como um estado que se acumula e PAUSA o processo (regra 5 da
  047) — dois modelos de "unidade com problema" genuinamente diferentes, não a mesma
  coisa com nomes diferentes. Forçar um `SyncJob[T]` com um contrato só para os dois teria
  exigido ou (a) um design genérico o bastante para não perder nenhuma das duas nuances —
  na prática, tão genérico quanto duas classes concretas, só que com uma camada de
  indireção a mais — ou (b) apagar uma das distinções pra caber no molde. Nenhuma opção
  reduz risco ou complexidade de verdade. O que É genuinamente igual — "toda execução
  produz um registro de histórico com contadores e erro" — foi extraído: `sync_runs`
  (antes `term_sync_runs`, só do DJEN) ganhou `lawsuit_id`/`integration`, e
  `MovementSyncService.sync_lawsuit` agora abre/fecha uma run como o
  `TermSyncService._execute` sempre fez. Ganho concreto sem inventar abstração.
- **Auditoria de caos (alvo 2) achou 2 bugs reais, não só teoria.** (1) `_create_key_rotated_alert`
  (spec 046) não deduplicava — um lote inteiro de processos batendo 401 no DataJud criava
  um `IntegrationAlert` POR PROCESSO, inundando o painel/banner. (2) `sync_due` tratava
  401 como erro-por-processo igual a qualquer outro, insistindo no próximo processo do
  lote mesmo sabendo que a causa (chave inválida) é global — desperdiçava chamada contra
  um rate limit já sabido inútil. Os dois corrigidos: dedup via
  `IntegrationAlertRepository.get_open_by_code` (reaproveitado da 049) e o lote agora
  para no primeiro 401, retomando no próximo agendamento.
- **Normalização de número de processo estava implementada 3 vezes** (`br_documents.
  strip_document_mask`, `djen/parser.py::normalize_process_number`,
  `datajud/parser.py::normalize_process_number`) com o mesmo regex `\D` copiado. Os dois
  parsers passaram a delegar a limpeza pro helper de `core` — a assinatura/regra de `None`
  de cada um continua diferente de propósito (cada call site trata ausência de forma
  diferente), só o "tirar tudo que não é dígito" ficou em um lugar.
- **`lawsuit_subjects` (spec 047) tinha RLS mas nenhum teste provando isolamento** — RLS
  "por padrão" nunca é suficiente sozinho; o CLAUDE.md §4 pede o teste explícito por
  tabela nova, e essa tinha ficado pra trás. Adicionado.
- **Fixtures HTTP com dado real de pessoa identificável — achado e NÃO corrigido de
  propósito.** ~40 testes de 042-047 dependem do conteúdo exato dos fixtures gravados ao
  vivo do DJEN/DataJud (CPF e nomes reais, ainda que legalmente públicos). Anonimizar sem
  mapear toda asserção dependente arrisca quebrar "teste passa sem edição" — o oposto do
  que uma refatoração deve fazer. Registrado como dívida (#19), não forçado.
- **Dívida #17 (wall-clock) investigada de novo, sem alvo de código encontrado.**
  `create_engine_from_url` usa pool padrão do SQLAlchemy, mas o pool enche sob demanda —
  um teste típico abre 1 conexão de qualquer forma, então `pool_size` menor não muda o
  custo real por teste. A hipótese registrada na 033 não se sustenta na leitura do
  código; o custo é dominado por handshake de conexão nova (fixtures function-scoped,
  sem reuso) + contenção do host compartilhado — nenhum dos dois é redutível por
  configuração de pool. Item re-atribuído à 098 com recomendação mais específica
  (dividir a suíte em grupos paralelos por domínio), não mais "reduzir custo de boot".

## Financeiro — exatidão numérica e agregação (spec 060)

- **Auditoria numérica (Alvo 1): zero `float` em caminho de dinheiro, confirmado por
  leitura, não por grep automatizado no CI (fora de escopo desta spec).** Todo campo
  monetário é `NUMERIC(14,2)` no banco e `Decimal` no Python, do model ao service. Os
  únicos `float` encontrados no domínio financeiro/CRM são: (1) `delta_pct`/`pct` em
  `lawsuits/stats.py` — percentuais de variação de CONTAGEM (processos, fechamentos),
  não dinheiro; (2) `JsonDecimal` (`app/core/schemas.py`) — converte `Decimal → float`
  só na fronteira de serialização JSON (JSON não tem tipo Decimal nativo), depois que
  todo o cálculo já aconteceu em `Decimal`. Nenhum dos dois é "float no caminho de
  dinheiro" — são os dois pontos onde a saída deixa de ser dinheiro (é razão ou é wire
  format) e vira número de exibição.
- **Arredondamento: `ROUND_HALF_UP` só onde já existia (`_split_amount`, spec 057) —
  em todo o resto o valor nunca é arredondado, só somado/subtraído.** `Decimal` com 2
  casas fixas não acumula erro de ponto flutuante em soma/subtração; arredondamento só
  entra quando um total é DIVIDIDO (parcelamento), e ali o resto sempre vai pra última
  parcela (regra 2, spec 057) — testado agora para todo N de 2 a 100, não só os poucos
  N cobertos nos testes originais da 057 (`test_installment_split.py`).
- **Rodapé da listagem de lançamentos (spec 059, regra 9) somava no CLIENTE — achado
  e corrigido.** `TransactionsListPage.tsx` reduzia `transactions.map(amount)` em
  JavaScript para montar "total/saldo/previsto", violando a regra desta própria
  auditoria ("a UI só formata"). Virou `GET /transactions` devolvendo `totals` já
  somado no banco, com o MESMO filtro da página (`TransactionRepository.
  totals_filtered`, reaproveitando `_filter_conditions` de `list_filtered` — nenhuma
  duplicação de WHERE entre os dois). O front só chama `formatBrl(data.totals.x)`.
- **Exceção mantida conscientemente: `InstallmentFields.tsx` (spec 057) calcula o
  preview de parcelas em JS antes de salvar.** Diferente do rodapé, este cálculo NUNCA
  é a fonte da verdade — é só uma prévia; o valor que de fato persiste vem sempre do
  `_split_amount` do backend na criação, e a paridade entre os dois já tem teste
  próprio (`lib/installments.ts` espelhando `_split_amount`, spec 057). Não é a mesma
  classe de violação do rodapé (que exibia o resultado do cálculo como se fosse dado
  real, sem contraparte no backend).
- **Saldo da view materializada = soma direta, verificado por SQL cru e não pelo
  mesmo código de produção auditado.** `test_saldo_da_view_bate_com_soma_direta_no_
  mesmo_dataset` cruza `account_daily_balances_visible` contra um `SUM(CASE...)`
  escrito à mão no teste — um bug nos dois lugares (view e query de produção) não
  passaria batido se o teste reusasse a mesma lógica Python.
- **`MaterializedAggregate` (Alvo 2) — extraído `app/core/materialized_view.py`.**
  `user_monthly_scores` (039) e `account_daily_balances` (059) tinham o mesmo REFRESH
  CONCURRENTLY/AUTOCOMMIT/superusuário copiado ponto a ponto. Virou uma função
  compartilhada (`refresh_materialized_view_concurrently`) + um registro central
  (`MATERIALIZED_VIEWS`, com `refresh_interval_minutes` por view) que as 4 views de BI
  (074–077) reusam quando chegarem. O wrapper de cada worker (`refresh_user_monthly_
  scores`, `refresh_account_daily_balances`) ficou só como nome/assinatura estável
  pros testes existentes, delegando pro helper. A "métrica de defasagem exposta na
  UI" também sai do registro (`MaterializedViewSpec.staleness_hint()`), não de uma
  string solta no componente — `TransactionStatsResponse.balance_staleness_hint`.
- **Permissão financeira (Alvo 3) — 2 vazamentos reais achados e corrigidos.** (1)
  `GET /lawsuits/{id}/financial-summary` só exigia `require_role(COLABORADOR)`, sem
  gate de `financial_access` — qualquer colaborador via `received`/`to_receive`/
  `expenses` de qualquer processo. Ganhou `require_financial(READ_ONLY)` (403 para
  `NONE`, mesma dupla-`Depends` já usada em `financial-categories`). (2) `GET /crm/
  board` e `GET /crm/stats` mostravam `case_value`/`total_value`/`stagnant_value` sem
  checar `financial_access` — corrigido nulando esses 3 campos (não bloqueando o
  endpoint inteiro, que continua servindo pra quem só precisa navegar processos)
  quando `financial_access=NONE`, mesmo padrão já usado para `users.salary` (spec
  012). `test_permission_coverage.py` (mesmo espírito da spec 005) só prova que toda
  rota declara ALGUMA permissão — não que o NÍVEL é o certo; `test_financial_
  permission_sweep.py` é a peça nova que varre as rotas financeiras de verdade.
- **`KanbanBoard` (spec 051) tinha 2 strings de domínio ("Nenhum processo", "Nenhuma
  fase configurada") coladas no componente genérico — achado e corrigido.** Viraram
  props (`emptyColumnMessage`/`emptyBoardTitle`/`emptyBoardDescription`) com default
  neutro; `CrmPage.tsx` passa os textos de processo explicitamente. O teste do
  componente genérico (`KanbanBoard.test.tsx`) precisou passar a prop — o próprio
  título do teste já dizia "sem conhecer domínio", e o componente agora cumpre.
- **Banco: `ix_tx_open`/`ix_tx_effective` confirmados em uso com 100k lançamentos**
  (seed isolado, mesmo padrão da medição de 20k da spec 040 — não uma suíte
  permanente). `EXPLAIN ANALYZE` real: atrasados (filtro `due_date`+`payment_date
  IS NULL`) usa `ix_tx_open`, 18ms; gráfico por vencimento (filtro `NOT is_internal`+
  intervalo de datas) usa `ix_tx_effective`, 8ms. O agregado de previsto/realizado por
  regime (`period_totals`) faz *Seq Scan* a 100k linhas — correto pelo plano (o filtro
  cobre ~metade da tabela nesse teste sintético, seq scan é mais barato que bitmap ali
  de verdade), e ainda assim 25ms — bem dentro do teto de 300ms do DoD desta spec.
  Nenhuma mudança de índice foi necessária.
- **`lawsuit_stage_history` sem política de retenção — investigado, NÃO implementada
  de propósito.** Ao contrário de `external_requests` (spec 041, 30 dias — log de API
  descartável), o histórico de fase é dado de negócio (tempo em cada etapa, auditoria
  de processo) que um usuário pode querer consultar anos depois; decidir um prazo de
  expurgo é decisão de produto, não engenharia, e apagar errado é irreversível. Sem
  sinal de que o volume hoje é um problema prático (linha pequena, 1 insert por troca
  de etapa). Deixado registrado aqui para uma spec futura decidir o prazo com dono de
  produto, em vez de uma refatoração adivinhar.
- **Causa raiz real de um flake que 3 specs anteriores (051/052/058) já tinham hit e
  atribuído a "banco sujo de execução ad-hoc" sem resolver.** `test_datajud_401_
  permanente_para_o_lote_sem_duplicar_alerta` (`test_resilience_chaos.py`, spec 050)
  usa `session.begin()` (precisa ler de volta numa sessão separada), diferente do
  padrão "só `flush`, nunca commit" documentado e seguido pelos outros testes do mesmo
  domínio — e por isso commitava de verdade um `IntegrationAlert` de SISTEMA
  (`tenant_id` nulo, visível a QUALQUER tenant pela política de RLS da migration 046)
  sem nunca limpar. Isso quebrava `test_sync_observability.py` deterministicamente
  toda vez que a suíte inteira rodava — reproduzível mesmo com o banco recém-limpo,
  não só em runs sujos. Corrigido com um `DELETE` explícito no teste culpado ao final
  (higiene de teste, zero mudança na regra de produto verificada).

## Refatoração 080 — isolamento e performance do BI

### Refresh das views com volume real

Medido em 2026-08-26 com `backend/scripts/bench_aggregates.py` (script, não teste — a
suíte não paga esse custo): um tenant descartável com **100.000 processos, 500.000
tarefas e 200.000 lançamentos** (seed em 140 s), `REFRESH MATERIALIZED VIEW
CONCURRENTLY` das oito views do registry, sequencial, como o beat faz.

| View | Segundos | Linhas |
|---|---|---|
| `user_monthly_scores` | 1,68 | 223 |
| `account_daily_balances` | 0,14 | 146 |
| `agility_daily` | 1,70 | 609 |
| `timesheet_daily` | 0,05 | 30 |
| `bi_pipeline_monthly` | 0,19 | 1.723 |
| `bi_vintage` | 0,09 | 343 |
| `bi_lawsuit_cycles` | 1,77 | 34.164 |
| `bi_cost_allocation` | 0,42 | 205 |

**Nenhum refresh passa de 2 s** — trinta vezes abaixo do teto de 60 s da spec 080 e do
limiar que dispara alerta (`SLOW_REFRESH_ALERT_SECONDS`, spec 078 regra 9). As três
views mais caras são exatamente as que varrem as tabelas grandes (`post_users` nas
duas de produtividade, `lawsuits` fechados na de ciclos); as demais agregam sobre
recortes pequenos. **Refresh incremental não se justifica** — a complexidade de manter
delta por tenant não paga 1,8 s a cada 8 horas. Reavaliar quando uma view passar de
10 s, não antes.

`CONCURRENTLY` confirmado sem bloqueio de leitura: com o refresh de
`bi_lawsuit_cycles` em curso (1,08 s), um `SELECT` concorrente na mesma view respondeu
em 0,05 s. As oito views têm índice único, requisito do `CONCURRENTLY` — e o plano de
leitura pela view barreira usa esse índice (`Bitmap Index Scan on ux_bi_cycles`), não
varredura sequencial.

O refresh sequencial usa **uma conexão por vez** (`refresh_due_aggregates` chama
`refresh_aggregate` em série, cada um com o próprio engine descartável): não há como
estourar o pool com oito refreshes simultâneos, porque simultâneos eles não são.

### `aggregate_refresh_log` era a única tabela sem teto

A auditoria de retenção encontrou o furo: o beat de 1 minuto grava uma linha por view
refrescada (10–12 mil linhas/dia em regime) e a spec 078 criou a tabela sem expurgo.
Retenção de 90 dias (mesmo horizonte de `sync_runs`), beat diário
`aggregate-refresh-log-purge`. `access_logs` já tinha o expurgo mensal de 12 meses da
spec 073.

### Divisão por zero num lugar só

`app/core/ratios.py` (`safe_ratio`/`safe_percentage`) substitui nove condições
`if denominador > 0 else None` espalhadas por BI, relatórios e taskscore. A regra que
elas escondiam é de produto, não de aritmética: **zero é um diagnóstico, `None` é a
ausência dele** — "0% de conversão" e "nenhuma oportunidade no período" não podem
aparecer iguais num relatório. O arredondamento acontece uma vez, no fim (arredondar o
quociente antes de multiplicar por 100 move a casa decimal), e `digits=None` devolve o
quociente cru para quem formata depois.

### Fronteira do tenant: ver `SEGURANCA-RLS.md`

O inventário completo das 56 políticas, das 6 exceções e das 12 funções
`SECURITY DEFINER` ficou em documento próprio, com o teste que sustenta cada linha.

## Ambiente de execução do agente (não é decisão de produto)

- Este sandbox resolve Postgres/Redis via o hostname `dind` (Docker-in-Docker remoto), não
  `localhost` — peculiaridade só deste ambiente de desenvolvimento assistido. `.env.example`
  continua correto com `localhost` para qualquer máquina real; overrides via `TEST_*`/
  `PYTEST_ALLOW_HOSTS`/`DATABASE_URL` explícitos resolvem isso sem contaminar config
  commitada.
