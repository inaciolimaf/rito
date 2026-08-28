# 101 — Correção dos stubs desbloqueados e da dívida nomeada

**Fase:** 10 · **Tipo:** correção · **Orçamento:** +12 s no wall-clock
**Depende de:** 015, 016, 019, 022, 023, 054, 055, 056, 058, 082, 090 · **Status:** ⬜ pendente

---

## 1. Objetivo

Fechar a diferença entre o que as specs 013–100 escreveram que fariam e o que o código faz.
Todo item aqui tem a mesma origem: uma spec anotou nas Descobertas “resolvo quando a spec NNN
chegar”, a NNN chegou, e ninguém voltou — o comentário no código continua dizendo que a
dependência não existe. Depois desta spec, excluir uma etapa, uma origem, uma categoria, um
centro de custo ou uma conta **em uso** devolve 409 em vez de 500; o saldo bancário é o saldo;
o dashboard de contatos para de publicar um número constante; “Configurações” abre; e quem
esquece a senha recebe o e-mail.

> Esta spec **muda comportamento** de propósito — não é refatoração. Testes que hoje provam o
> no-op (`test_excluir_etapa_nao_bloqueia_ainda`, `test_excluir_nao_bloqueia_ainda` ×2) são
> reescritos, não preservados. São os únicos.

## 2. Escopo

Cinco blocos. A ordem importa: A e B mexem no banco, C e D não.

### Bloco A — stubs cuja dependência já chegou

- **Etapas** (`stages`, spec 015): `transfer()` reatribui `lawsuits.stage_id` de verdade e
  `delete()` ganha guarda de “em uso”. A dependência (`lawsuits.stage_id`, FK `NOT NULL`)
  existe desde a spec 022 — 78 specs atrás. **Não está no `DIVIDA-TECNICA.md`**: o item nº 13
  cita este caso e o classifica como “ainda genuinamente bloqueado”, o que deixou de ser verdade.
- **Origens de pessoa** (`customer_origins`, spec 016): idem, sobre `customers.origin_id`,
  que existe desde a spec 017. É a **dívida nº 13**.
- **Contatos com processo ativo** (spec 019): o filtro `has_active_lawsuit` e os contadores
  `with_active_lawsuit`/`without_active_lawsuit` do `/customers/stats` deixam de ser stub.
  `lawsuit_parties` (com `customer_id` e `is_client`) existe desde a spec 023.
  **Não está no `DIVIDA-TECNICA.md`.**
- **Categorias e centros de custo** (specs 054/056): guarda de “em uso” e reatribuição real
  sobre `transactions`. Metade da **dívida nº 20**.
- **Contas e cartões** (specs 055/056/058): saldo real, fatura do ciclo, guarda de exclusão e
  `initial_amount` imutável depois do 1º lançamento. Outra metade da **dívida nº 20** —
  inclusive o `NOT is_internal` que a 058 deixou anotado para não esquecer.

### Bloco B — as duas divergências de taxonomia

- **Dívida nº 11:** `uq_squads_tenant_name` vira índice único normalizado
  (`immutable_unaccent(lower(name))`), como as outras quatro taxonomias desde a 014, com
  migration de dado para os duplicados que hoje são válidos.
- **Dívida nº 12:** a busca `q` das 5 taxonomias passa a ignorar acento, como
  `CustomerRepository.list_filtered` já faz desde a 019.

### Bloco C — navegação e e-mail transacional

- **Rota `/settings`:** o item “Configurações” da sidebar aponta para uma rota que não existe e
  cai no `NotFoundPage`. **Não está no `DIVIDA-TECNICA.md`.**
- **E-mail transacional:** `forgot_password` gera o token e ninguém o envia — o fluxo de
  recuperação de senha não tem saída. Junto vêm o convite de usuário (spec 012) e o de parceria
  (spec 079), que hoje contornam devolvendo o token no corpo da resposta, e a tela de aceitar
  convite (**dívida nº 9**, reclassificada como “produto” na 100).

### Bloco D — `SAVEPOINT` no avanço do nó

- A dívida sem número do fim do `DIVIDA-TECNICA.md` — a única cuja spec-alvo era a **100**, e a
  única que ficou de fora da tabela de fechamento dela justamente por não ter número.

### Bloco E — acerto do registro (sem código de produção)

- Numerar a dívida do `SAVEPOINT` como **nº 21**, acrescentar como **nº 22, 23 e 24** os três
  itens desta spec que não estavam rastreados (etapas, contatos com processo ativo, rota
  `/settings`), e registrar os três handoffs perdidos (085→090, 079→080, 038→086).
- Corrigir a contagem de metas de p95 em `docs/PERFORMANCE.md` e em `specs/100-*.md` §9:
  são **sete** metas, quatro passam — não “cinco das oito”.
- Fechar as dívidas **nº 15** e **nº 16** com decisão explícita (ver §7, regras 22 e 23).

## 3. Fora de escopo

- **Dívida nº 18 — cálculo de prazo fatal.** Contagem de dias úteis por classe/assunto do CNJ é
  um problema em si, não um stub esquecido. Fica para uma spec própria — que precisa existir:
  a 038 e a nº 18 endereçaram esta dívida “para a spec 086”, e a 086 virou *IA de intimações*.
  Renomear o destinatário faz parte do Bloco E; implementar, não.
- **Seed de feriados de 2031 em diante** (spec 038) — entra na mesma spec de prazos. Aqui só
  vira linha no `DIVIDA-TECNICA.md`, que é onde deveria estar desde a 038.
- **Jornada e2e 11/25 do copiloto** (handoff 085→090) e **view de inbox unificada de parceiros**
  (handoff 079→080). Ambos são decisões de escopo com custo real, não correções: entram como
  linha rastreada, não como trabalho.
- **Índice único normalizado em qualquer outra tabela** além de `squads`.
- **Preferência de notificação por evento** e qualquer canal além de e-mail — o Bloco C liga o
  SMTP que já existe (`app/integrations/messaging/`) aos três fluxos de autenticação, nada mais.

> Fora de escopo é vinculante. Se durante a implementação surgir algo daqui,
> anote em `## 9. Descobertas` e siga — não implemente.

## 4. Modelo de dados

Nenhuma tabela nova. Uma migration, `alembic/versions/101_squads_unaccent_unique.py`
(`down_revision = "099_migration_lock"`):

```sql
-- Dívida nº 11. As outras 4 taxonomias usam esta forma desde a migration 014.
-- immutable_unaccent() já existe (criada em 014_action_groups_types.py).

-- 1. Desempate determinístico ANTES de criar o índice: o mais antigo mantém o nome,
--    os demais ganham sufixo. Renomear, nunca apagar — squad_members tem FK para squads.
WITH ranked AS (
    SELECT id,
           name,
           row_number() OVER (
               PARTITION BY tenant_id, immutable_unaccent(lower(name))
               ORDER BY created_at, id
           ) AS rn
    FROM squads
)
UPDATE squads s
SET name = s.name || ' (' || r.rn || ')'
FROM ranked r
WHERE s.id = r.id AND r.rn > 1;

-- 2. Troca a constraint pelo índice normalizado.
ALTER TABLE squads DROP CONSTRAINT uq_squads_tenant_name;
CREATE UNIQUE INDEX uq_squads_tenant_name
    ON squads (tenant_id, immutable_unaccent(lower(name)));
```

`downgrade()` refaz o caminho inverso (dropa o índice, recria a constraint) e **não** desfaz o
rename — desfazer exigiria saber qual sufixo foi nosso, e um downgrade que adivinha é pior que
um que não tenta. Registrar isso no docstring da migration.

O modelo SQLAlchemy (`app/domain/squads/models.py:16`) perde o `UniqueConstraint` do
`__table_args__` — o índice funcional não é declarável ali, igual às outras quatro.

## 5. Contratos de API

Nenhuma rota nova. Catorze rotas existentes passam a se comportar como o contrato já dizia.

| Método | Rota | Entrada | Saída | Autorização |
|---|---|---|---|---|
| DELETE | `/api/v1/stages/{id}` | — | `204` · **`409` se em uso** | GESTOR |
| POST | `/api/v1/stages/transfer` | `{from_id,to_id}` | `200 {transferred_count}` **real** | GESTOR |
| DELETE | `/api/v1/customer-origins/{id}` | — | `204` · **`409` se em uso** | GESTOR |
| POST | `/api/v1/customer-origins/transfer` | `{from_id,to_id}` | `200 {transferred_count}` **real** | GESTOR |
| GET | `/api/v1/customers?has_active_lawsuit=` | `bool` | `200 {items,next_cursor,total}` **filtrado de verdade** | qualquer autenticado |
| GET | `/api/v1/customers/stats` | — | `200 {…, with_active_lawsuit, without_active_lawsuit}` **calculados** | qualquer autenticado |
| DELETE | `/api/v1/financial-categories/{id}` | — | `204` · **`409` se em uso** | `financial.write` |
| POST | `/api/v1/financial-categories/transfer` | `{from_id,to_id}` | `200 {transferred_count}` **real** | `financial.write` |
| DELETE | `/api/v1/cost-centers/{id}` | — | `204` · **`409` se em uso** | `financial.write` |
| POST | `/api/v1/cost-centers/transfer` | `{from_id,to_id}` | `200 {transferred_count}` **real** | `financial.write` |
| DELETE | `/api/v1/bank-accounts/{id}` | — | `204` · **`409` se tem lançamento** | `financial.write` |
| PUT | `/api/v1/bank-accounts/{id}` | `BankAccountUpdateRequest` | `200` · **`409` se `initial_amount` mudou com lançamento** | `financial.write` |
| GET | `/api/v1/bank-accounts/{id}/balance` | `at=` | `200 {amount}` **saldo real** | `financial.read` |
| GET | `/api/v1/bank-accounts/balances` | — | `200 [{…, is_invoice}]` **saldo/fatura reais** | `financial.read` |

Autorização de cada rota é a que já existe — nenhuma muda de perfil.

Erros (RFC 7807): `409` novo em seis rotas, com `detail` no mesmo formato do precedente da spec
014 (`"Grupo tem tipos de ação vinculados — transfira-os antes de excluir."`). Cada domínio
ganha sua exceção própria (`StageInUseError`, `CustomerOriginInUseError`,
`FinancialCategoryInUseError`, `CostCenterInUseError`, `BankAccountInUseError`,
`InitialAmountLockedError`), no padrão de `ActionGroupInUseError`.

`POST /api/v1/auth/forgot-password` continua `202` sem corpo — o que muda é que agora o e-mail
sai. `POST /api/v1/users/{id}/invite` e `POST /api/v1/partnerships/invite` **param de devolver
o token** no corpo: o link vai por e-mail, e devolver o segredo numa resposta HTTP era o
contorno, não o contrato.

## 6. Front-end

**Componentes reutilizados:** `TransferBeforeDeleteDialog`, `ConfirmDialog`, `FormModal`,
`DataTable`, `StatCard`, `EmptyState`.

**Componentes criados:** nenhum. `TransferBeforeDeleteDialog` já existe desde a 014 e hoje só
está plugado em `ActionGroupsListPage` e `TaskTypesListPage` — as Descobertas das specs 015 e
016 registram, em texto, que ele *não* foi plugado nas telas de etapas e de origens. Plugar nas
quatro telas restantes (etapas, origens, categorias, centros de custo) é o item de front do
Bloco A, e é o terceiro e quarto uso do componente: a regra dos 3 usos já foi paga.

**Rotas:**
- `/settings` — **nova**. Hub de configurações, listando as 16 telas de configuração já existentes
  agrupadas por assunto (Escritório, Cadastros, Processos, Financeiro, Automação, IA). É o
  destino que `navItems.ts:42` já aponta desde a spec 008.
- `/accept-invite` — **nova**. Recebe `?token=`, pede nome e senha, chama o endpoint de aceite
  que já existe no backend, redireciona para `/login`. Serve o convite de usuário e o de
  parceria (o backend distingue pelo token).

**Estados:** loading, vazio, erro, sem permissão. Em `/settings`, cada grupo esconde o que o
perfil não pode ver — a mesma `capability` que já filtra o item na sidebar
(`settings.manage`, `financial.read`).

**Enums espelhados (dívida nº 15):** decisão registrada em §7, regra 21 — sem código novo aqui
se a decisão for “ainda não”.

## 7. Regras de negócio

### Bloco A — stubs

1. Excluir uma etapa referenciada por ao menos um processo (`lawsuits.stage_id`) devolve `409`
   e não apaga nada.
2. `POST /stages/transfer` reatribui todos os `lawsuits` da etapa de origem para a de destino e
   devolve a contagem real em `transferred_count`; depois dele, a exclusão da etapa de origem passa.
3. Excluir uma origem referenciada por ao menos um contato (`customers.origin_id`) devolve `409`.
4. `POST /customer-origins/transfer` reatribui `customers.origin_id` de verdade e devolve a
   contagem real.
5. `GET /customers?has_active_lawsuit=true` devolve exatamente os contatos que são parte
   (`lawsuit_parties`) de ao menos um processo com `is_archived = false`; `=false` devolve o complemento;
   omitido não filtra.
6. `with_active_lawsuit` + `without_active_lawsuit` do `/customers/stats` somam `total`, e
   `with_active_lawsuit` bate com a contagem da regra 5 sobre a mesma base.
7. Excluir uma categoria financeira ou um centro de custo com lançamento vinculado devolve `409`.
8. `POST /financial-categories/transfer` e `POST /cost-centers/transfer` reatribuem os
   `transactions` de verdade e devolvem a contagem real.
9. O saldo de uma conta é `initial_amount` + entradas pagas − saídas pagas, **ignorando
   `transactions.is_internal`** (regra 1 da spec 058). Sem lançamento, continua sendo
   `initial_amount` — os testes atuais de 054/055 seguem válidos.
10. Para conta do tipo `CARTAO_CREDITO`, `/balance` devolve a fatura do ciclo em aberto
    (`cycle_day`/`due_day`), não o saldo — e `is_invoice` continua marcando a diferença em
    `/bank-accounts/balances`.
11. Excluir uma conta com ao menos um lançamento devolve `409`.
12. `initial_amount` não pode ser alterado depois do 1º lançamento da conta: `PUT` com valor
    diferente devolve `409`; com o mesmo valor, passa.

### Bloco B — taxonomias

13. Criar um time cujo nome só difere de um existente por caixa ou acento devolve `409`
    (“Time A” × “TIME A” × “Timé A”), como já acontece nas outras quatro taxonomias.
14. A migration renomeia os duplicados pré-existentes mantendo o mais antigo intacto, sem
    apagar nenhum time e sem tocar em `squad_members`.
15. A busca `q` de times, grupos de ação, tipos de ação, etapas e origens encontra o registro
    independentemente de acento e de caixa, nos dois sentidos (buscar “etica” acha “Ética”, e
    buscar “Ética” acha “etica”).

### Bloco C — navegação e e-mail

16. `/settings` responde com o hub e não com o `NotFoundPage`, e o item “Configurações” da
    sidebar chega lá em um clique.
17. Toda entrada de `NAV_ITEMS` com `path` corresponde a uma rota declarada em `App.tsx` —
    verificado por teste, não por inspeção (ver §8).
18. `POST /auth/forgot-password` envia um e-mail contendo o link com o token para o endereço
    informado, e continua respondendo `202` mesmo quando o e-mail não existe (não vaza
    existência de conta — regra da spec 004, preservada).
19. Convite de usuário e de parceria enviam o link por e-mail e **não** devolvem o token na
    resposta HTTP.
20. Sem `SMTP_HOST` configurado, o envio levanta `ChannelNotConfiguredError`, é registrado em
    log e **não** derruba a operação — o mesmo comportamento silencioso da spec 061/069. O
    token continua sendo criado; o que falha é a entrega.

### Bloco D — runtime de IA

21. Um timeout de nó que cai dentro de uma query deixa a sessão utilizável: o `_fail()` grava o
    passo de erro e o `thread` termina em `ERROR` com a mensagem de timeout, sem
    `PendingRollbackError`. Implementação: `session.begin_nested()` em volta do avanço do nó em
    `app/ai/runtime.py`, como `AiActionService.approve` (084) e `AutomationEngine.advance` (092)
    já fazem. Os testes da 082 rodam junto e passam sem edição.

### Bloco E — registro

22. **Dívida nº 15 (enums TS espelhados):** contar quantos StrEnum de domínio cruzam a
    fronteira da API hoje. Três ou menos → registrar “abaixo do gatilho da regra dos 3 usos,
    reavaliar no quarto” e fechar a linha com data. Quatro ou mais → o `scripts/dump-enums`
    entra nesta spec. A decisão é do número, não do gosto.
23. **Dívida nº 16 (“listagem nova custa < 80 linhas”):** medir a listagem mais recente
    (`/settings` não serve — não é listagem; usar a de times, tocada no Bloco B), registrar a
    contagem em `test-timing.json` e fechar a dívida com o número medido, seja ele qual for.
24. `docs/DIVIDA-TECNICA.md` termina esta spec sem nenhum item cuja spec-alvo já tenha passado,
    e sem item sem número.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| integração | etapa em uso → 409; transfer reatribui e libera a exclusão (regras 1–2) | `tests/integration/test_stages.py` | ~0,6 s |
| integração | origem em uso → 409; transfer reatribui (regras 3–4) | `tests/integration/test_customer_origins.py` | ~0,6 s |
| integração | filtro e contadores de processo ativo (regras 5–6) | `tests/integration/test_customers_listing.py` | ~0,8 s |
| integração | categoria/centro em uso → 409 e transfer real (regras 7–8) | `tests/integration/test_financial.py` | ~0,8 s |
| integração | saldo com lançamentos, `is_internal` fora, fatura de cartão (regras 9–10) | `tests/integration/test_bank_accounts.py` | ~1,0 s |
| integração | conta com lançamento não some; `initial_amount` trava (regras 11–12) | `tests/integration/test_bank_accounts.py` | ~0,6 s |
| integração | nome de time colidindo por caixa/acento → 409 (regra 13) | `tests/integration/test_squads.py` | ~0,4 s |
| migration | duplicados renomeados, nenhum time perdido, membros intactos (regra 14) | `tests/integration/test_migration_101.py` | ~0,5 s |
| integração | busca sem acento nas 5 taxonomias, um caso por entidade (regra 15) | `tests/integration/test_taxonomy_search.py` | ~0,7 s |
| integração | forgot-password envia pelo canal mockado; e-mail inexistente também dá 202 (regra 18) | `tests/integration/test_auth.py` | ~0,4 s |
| integração | convite não devolve token e dispara envio (regra 19) | `tests/integration/test_users.py` | ~0,4 s |
| unit | canal não configurado não derruba a operação (regra 20) | `tests/unit/test_messaging.py` | ~0,1 s |
| integração | timeout dentro de query grava o erro e não corrompe a sessão (regra 21) | `tests/integration/test_ai_threads.py` | ~0,5 s |
| RLS | transfer/exclusão de etapa, origem, categoria, centro e conta não cruzam tenant | `tests/integration/test_rls_corrections.py` | ~0,8 s |
| meta | **toda entrada de `NAV_ITEMS` com `path` resolve para uma rota de `App.tsx`** (regra 17) | `tests/meta/test_final_audit.py` | ~0,1 s |
| meta | **nenhum comentário de produção cita “spec NNN” já concluída como pendente** | `tests/meta/test_final_audit.py` | ~0,2 s |
| meta | **todo item aberto do `DIVIDA-TECNICA.md` tem número e spec-alvo maior que a última ✅** (regra 24) | `tests/meta/test_final_audit.py` | ~0,1 s |
| frontend | `/settings` lista os grupos e esconde o que a capability não permite (regra 16) | `src/features/settings/SettingsHubPage.test.tsx` | ~0,3 s |
| frontend | `TransferBeforeDeleteDialog` plugado nas 4 telas restantes | `src/features/**/…ListPage.test.tsx` | ~0,6 s |
| frontend | `/accept-invite` valida token, envia, redireciona | `src/features/auth/AcceptInvitePage.test.tsx` | ~0,3 s |
| e2e | jornada 14/25: sidebar completa — derivada de `ROUTABLE_NAV_ITEMS`, não de cópia manual | `e2e/tests/navigation.spec.ts` | ~2 s |

**Total estimado:** ~12 s
**Fixtures externas:** nenhuma chamada de rede. SMTP mockado pela interface de
`app/integrations/messaging/` — nenhum e-mail sai em teste.

### Os três meta-testes são metade do valor desta spec

Corrigir 13 itens é trabalho de um ciclo. Impedir que o 14º nasça é o que evita a spec 201.
Cada um fecha uma das três formas de a dívida escapar:

- **Comentário que cita spec já concluída.** É a assinatura exata dos Blocos A e B — cinco
  serviços dizendo “nada referencia isto ainda” sobre dependências que existem há dezenas de
  specs. O teste varre `app/` por `chega na spec NNN`, `só chega na NNN`, `até a spec NNN`,
  `spec NNN (Descobertas)` e falha se NNN estiver ✅ no `ROADMAP.md`. Sozinho, teria pegado as
  etapas, as origens, as categorias, as contas e a dívida nº 13.
- **Rota de navegação que não existe.** O `/settings` sobreviveu 92 specs porque
  `Sidebar.test.tsx` percorre `NAV_ITEMS` só para conferir que o link renderiza, e a jornada
  e2e “navegar por todos os módulos” itera uma **cópia manual** que omite justamente
  Financeiro, Configurações e Conta e assinatura. Derivar a jornada de `ROUTABLE_NAV_ITEMS`
  faz a cópia deixar de existir.
- **Item de dívida sem número ou com alvo vencido.** A dívida do `SAVEPOINT` escapou por não
  ter número — a tabela de fechamento da 100 conta itens numerados. E `DIVIDA-TECNICA.md`
  abre dizendo que “se uma spec-alvo já passou e o item continua aqui, a próxima refatoração
  decide”; isso é uma regra, e regra sem teste é intenção.

## 9. Descobertas

Preencher durante a implementação: problemas encontrados, decisões tomadas,
dívidas deixadas para a próxima spec de refatoração.

Duas coisas a conferir logo no começo, porque mudam o tamanho do Bloco A:

- Quantos `lawsuits`, `customers` e `transactions` existem por tenant em produção com
  referência às entidades que passam a ter guarda — se algum tenant já tem uma etapa “em uso”
  que ele esperava conseguir apagar, o 409 novo é uma mudança visível e merece nota de release.
- Se `TransactionRepository` já tem por onde contar referência por conta/categoria/centro. A
  spec 056 registra que um `account_is_referenced()`/`category_is_referenced()` chegou a ser
  esboçado e foi **removido de propósito** por ser código sem uso — reintroduzir é o caminho,
  não reinventar.

## 10. Definição de pronto

- [ ] Escopo implementado, nada além
- [ ] Todas as 24 regras de negócio com teste
- [ ] Teste de isolamento por tenant nos cinco fluxos de transferência/exclusão
- [ ] Os três meta-testes verdes, e cada um verificado falhando antes da correção
- [ ] Os três testes que provavam o no-op reescritos, e nenhum outro teste editado
- [ ] `make test` verde e wall-clock < 300 s
- [ ] `make lint` verde
- [ ] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário
- [ ] `docs/DIVIDA-TECNICA.md` sem item sem número e sem spec-alvo vencida
- [ ] `docs/PERFORMANCE.md` e `specs/100-*.md` §9 com a contagem certa de metas de p95
- [ ] `ROADMAP.md` com a linha da 101 em ✅
- [ ] Commit `fix(101): correção dos stubs desbloqueados e da dívida nomeada`

---

## Nota de execução

Treze itens em cinco blocos é mais do que um ciclo típico do `/loop` fecha. Se o ciclo não
fechar dentro do orçamento, o corte já está desenhado — os blocos são independentes e cada um
tem migration própria (só o B tem) e domínio próprio:

| Spec | Blocos | Por que corta aqui |
|---|---|---|
| 101 | A + E | Os cinco stubs são o mesmo bug repetido; o registro fecha junto porque é o que descreve os cinco |
| 102 | B + C | Uma migration de dado e duas telas novas — nada em comum com A, e o único trabalho de front |
| 103 | D | Mexe na semântica de checkpoint do runtime da 082 e merece rodar com os testes dela isolados, como a própria dívida pede |

Cortar assim mantém a regra do CLAUDE.md §8 (“uma spec por ciclo, não adiante trabalho da
próxima”) sem perder o mapa: os blocos foram escritos juntos porque têm a **mesma causa**, e é
essa causa que os três meta-testes do Bloco E fecham.
