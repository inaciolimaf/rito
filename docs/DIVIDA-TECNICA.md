# Dívida técnica consciente

> Entregável da spec 010 (refatoração da Fundação). Cada item tem uma **spec-alvo** —
> onde a dívida deve ser resolvida, não "algum dia". Se uma spec-alvo já passou e o item
> continua aqui, a próxima spec de refatoração precisa decidir: resolver agora ou
> re-atribuir com justificativa nova.

## 1. ~~`BaseRepository.list_paginated`/`build_keyset_query` não implementam o contrato de
   listagem do CLAUDE.md §6~~ — RESOLVIDO na spec 012

`GET /api/v1/users` foi o primeiro endpoint de listagem real (`account`, na 011, é 1:1 e
não precisou). `app/core/repository.py` ganhou `build_sorted_keyset_query` (ordena por uma
coluna escolhida + `id` como desempate, comparação de tupla `WHERE (col, id) > (v, id)`) e
`encode_cursor`/`decode_cursor` (base64). O `build_keyset_query`/`list_paginated` antigos
(só `id`, sem `sort_value`) foram mantidos como estão — ninguém os usa em produção, e
mexer neles quebraria `tests/unit/test_base_repository.py` sem necessidade; viram uma
função gêmea nova em vez de uma migração da antiga. `UserRepository.list_filtered` é quem
usa o keyset novo de verdade, com filtros de `role`/`is_active`/busca textual + `COUNT`
para o `total`.

## 2. ~~Frontend sem ferramenta de cobertura instalada~~ — RESOLVIDO na spec 020

`@vitest/coverage-v8@3.2.7` (mesma major do `vitest` já usado — a versão `4.x` mais
recente do pacote exige `vitest@4`, que quebraria o resto do projeto) entrou como
devDependency, com um script `test:coverage` separado (`vitest run --coverage`) — não
plugado em `npm run test`/`make test` por padrão, mesmo padrão do backend (`pytest --cov`
também é opt-in via flag, não faz parte do `addopts` default). Overhead medido: ~4-5 s
sobre os ~18-19 s da suíte sem cobertura — cabe folgado no orçamento de 90 s da spec 020.
Estado inicial: 63% de statements/lines, 74% de branches, 57% de functions — número para
acompanhar regressão a partir de agora, não uma meta a bater nesta spec.

## 3. `AuthService.reset_password` tem um branch defensivo inalcançável

`service.py:121` (`if user is None: raise InvalidResetTokenError`) nunca dispara na prática
— `password_reset_tokens.user_id` tem `ON DELETE CASCADE` para `users.id`, então um token
não pode sobreviver ao usuário que apagou (e não há endpoint de exclusão de usuário ainda).
Mantido como defesa de invariante (barato, correto, documenta a intenção), mas sem teste
de integração porque forçá-lo exigiria violar a FK de propósito.

**Spec-alvo:** nenhuma — reavaliar só se um endpoint de exclusão de usuário mudar o
`ondelete` da FK (ex.: soft-delete em vez de CASCADE), o que tornaria o branch alcançável
de verdade.

## 4. `LoginPage` pede o UUID cru do tenant, não um identificador amigável

Não existe endpoint público que resolva um "código do escritório"/subdomínio para o UUID
de tenant — o contrato de `/auth/login` (spec 004) não carrega esse identificador no corpo,
só o header `X-Tenant-Id`. UX correta e honesta para o estado atual do backend, mas ruim
para um produto real.

**Spec-alvo:** 011 (Escritório/account) — já registrado como descoberta da spec 006.

## 5. Estado "offline" do frontend não implementado

A spec 006 lista "offline" como um dos estados de UI, mas não há regra de negócio nem
teste correspondente na seção 8 dela — não há detecção de `navigator.onLine`/banner de
rede hoje.

**Spec-alvo:** alguma spec de sincronização/fila offline futura (ainda sem número).

## 6. `enable_rls()` (wrapper de migration) não tem teste automatizado direto

A função pura que gera o SQL (`enable_rls_statements`) tem teste unitário
(`test_rls_helper.py`); o wrapper de 2 linhas que chama `op.execute()` por statement dentro
de uma migration do Alembic não — ele só roda como subprocesso do Alembic, fora do
processo instrumentado pelo `pytest-cov`. Na prática é exercitado (com sucesso) toda vez
que `alembic upgrade head` roda, inclusive nesta spec.

**Spec-alvo:** nenhuma — aceito como limite estrutural de cobertura via `coverage.py`
contra subprocessos externos, não uma lacuna de teste real.

## 7. Sem teste de mutação formal

O checklist "sem teste que passe por acidente" foi verificado por inspeção manual (as
asserções checam valores/mensagens exatas, não só status code genérico), não por uma
ferramenta de mutation testing (`mutmut`, `cosmic-ray`). Com 572 statements e 99% de
cobertura de linha, o retorno de instalar uma ferramenta dedicada ainda é baixo.

**Spec-alvo:** reavaliar na 020 ou quando a base de código crescer o suficiente para
inspeção manual deixar de ser confiável.

## 8. `S3FileStorage._ensure_bucket` não cobre o branch de corrida (`BucketAlreadyOwnedByYou`)

O `create_bucket` só roda quando `head_bucket` falha (bucket não existe) — testado com um
nome de bucket nunca visto (spec 011). O catch de `BucketAlreadyOwnedByYou`/
`BucketAlreadyExists` (dois workers de `pytest -n auto` tentando criar o mesmo bucket ao
mesmo tempo) exigiria forçar uma corrida de verdade entre processos, o que não é
determinístico o suficiente para um teste confiável.

**Spec-alvo:** nenhuma — aceito, mesma categoria do item 6 (código correto, caminho de
erro só exercitável por condição de corrida real).

## 9. Sem página de "aceitar convite" no frontend

`POST /api/v1/invitations/accept` existe e está testado (spec 012), mas a seção 6
("Front-end") da spec só lista `/settings/users` e `/settings/users/:id` — nenhuma rota
pública para quem recebeu o convite definir nome/senha. O fluxo é funcionalmente completo
no backend, mas ninguém consegue *usá-lo* pela UI ainda; o link do e-mail de convite (que
também não existe — sem infra de e-mail, ver regras 1-2) não tem para onde apontar.

**Spec-alvo:** a spec que trouxer a infraestrutura de e-mail (envio real de convites/reset
de senha) — as duas coisas (enviar o e-mail e ter uma página que recebe o clique)
precisam nascer juntas.

## 10. `/settings/users` não tem link de navegação — só acessível por URL direta

`/settings` continua sendo o placeholder genérico (nenhuma spec ainda construiu uma
"home" de Configurações com sub-navegação, diferente de "Conta e assinatura" na 011, que
tinha um único sub-item e pôde redirecionar direto). `/settings/users` e
`/settings/users/:id` existem e funcionam, mas exigem digitar a URL.

**Spec-alvo:** a spec que desenhar a página-índice de Configurações (ainda sem número no
roadmap) — ela precisa linkar para `/settings/users` e para os módulos de configuração
das specs 013+.

## 11. `squads` é a única das 5 taxonomias simples (013-019) com nome único sensível a
    maiúsculas/acento

`uq_squads_tenant_name` (spec 013) é `UNIQUE(tenant_id, name)` puro — as outras 4
(`action_groups`/`lawsuit_types` da 014, `stages` da 015, `customer_origins` da 016) usam
`UNIQUE(tenant_id, immutable_unaccent(lower(name)))`, convenção introduzida justamente na
014 (spec 013 é anterior a ela). Hoje "Time A" e "TIME A" coexistem como times distintos no
mesmo tenant, diferente de qualquer outra taxonomia do sistema. Não foi corrigido na spec
020 porque mudar o índice único MUDA COMPORTAMENTO observável (dois registros hoje válidos
passariam a colidir com 409) — proibido em spec de refatoração (CLAUDE.md §8).

**Spec-alvo:** nenhuma spec de feature ainda toca `squads` de novo; resolver na próxima
spec que mexer no CRUD de times, com uma migration de dado (decidir o que fazer com times
duplicados que já existem) além do índice.

## 12. Busca textual das 5 taxonomias simples (013-019) não ignora acento, diferente de
    `customers` (019)

`CustomerOriginRepository.list_filtered`, `ActionGroupRepository.list_filtered`,
`LawsuitTypeRepository.list_filtered`, `StageRepository.list_filtered` e
`SquadRepository.list_filtered` filtram o campo `q` com `Model.name.ilike(f"%{query}%")`
puro — a checagem de duplicidade (`get_by_name`) dessas mesmas entidades já usa
`func.unaccent(func.lower(...))` (regra 1 de cada spec), só a busca da listagem ficou de
fora. `CustomerRepository.list_filtered` (spec 019) é o único que unaccenta os dois lados
da comparação. Não unificado na spec 020: ampliar o que a busca encontra é, em espírito,
uma mudança de comportamento (mesmo não quebrando nenhum teste hoje — nenhum teste
existente depende da busca NÃO encontrar uma variante acentuada), e a extração de um
`unaccented_search_filter` só vale a pena junto da correção, não separada dela.

**Spec-alvo:** a próxima spec que tocar qualquer uma dessas 5 telas de listagem — aplicar
`func.unaccent(func.lower(Model.name)).ilike(func.concat("%", func.unaccent(func.lower(literal(query))), "%"))`
(mesmo padrão de `app/domain/customers/repository.py`) nas 5 de uma vez, com teste
dedicado por entidade.

## 13. `CustomerOriginService.transfer`/`delete` continuam sem lógica real, mesmo com
    `customers.origin_id` já existindo desde a spec 017

Documentado como no-op nas Descobertas da spec 016 ("nada referencia `origin_id` ainda —
`customers` só chega na spec 017"). A spec 017 chegou, `customers.origin_id` é uma FK real
desde então, e a 019 até consome origens no dashboard — mas `transfer()` continua sempre
retornando `0` (não reatribui `customers.origin_id` de verdade) e `delete()` continua sem
guarda de "em uso" (excluir uma origem referenciada por um `customer` hoje estoura
`IntegrityError` não tratado → 500, em vez de um 409 com a mensagem de "transfira antes").
Mesma razão dos itens 11/12 para não resolver na 020: implementar a reatribuição real e o
guard de "em uso" é a definição de "mudar comportamento" (o teste
`test_excluir_nao_bloqueia_ainda` documenta e prova o no-op atual) — cabe a uma spec de
feature, não a este pente-fino. Comparar com `LawsuitTypeService.transfer` (spec 014, real
desde o início porque `lawsuit_types` e `action_groups` nasceram juntos) e
`StageService.transfer` (spec 015, no-op igual a este, mas ainda genuinamente bloqueado —
`lawsuits.stage_id` só chega na spec 022).

**Spec-alvo:** a spec que criar o consumidor real de `origin_id` além de `customers` (já
existe) — ou uma spec de correção dedicada, já que a dependência que faltava (017) já
chegou. Renomear/atualizar o comentário e o teste
`test_excluir_nao_bloqueia_ainda`/`test_transferencia_com_ids_validos_retorna_200` junto.

## 14. EXPLAIN das visões precisa ser revalidado com volume real

A checklist da spec 030 pedia `EXPLAIN ANALYZE` nas 12 visões "sem seq scan em tabela
grande". Rodado na 030 (registro em `docs/DECISOES.md`): o banco de dev tem dezenas de
linhas — seq scan é o plano ótimo nesse volume, mesmo com `enable_seqscan=off`, então o
exercício não prova nada sobre o comportamento em produção. Os índices das colunas de
predicado existem e foram conferidos em `pg_indexes`.

**Spec-alvo:** 098 (performance) — gerar massa sintética (10⁵+ processos por tenant) e
repetir o `EXPLAIN ANALYZE` das 12 visões + stats (028) + agrupamento por pasta (029).

## 15. Enums do banco espelhados à mão em TS

`PartyPoleApi`, `LawsuitOutcome`, `ContingencyLevel` e cia. são redeclarados como union
types em `frontend/src/features/*/api.ts` — duplicação manual que pode divergir do
StrEnum do backend sem nenhum alarme. A checklist da 030 pedia espelho "sem duplicação
manual"; gerar os unions TS a partir dos StrEnum via script (`scripts/dump-enums`)
continua pendente — o volume atual (3 enums) não justificou a infra nesta refatoração.

**Spec-alvo:** quando o 4º enum de domínio cruzar a fronteira da API (regra dos 3 usos)
— provavelmente status de tarefa (032) ou tipo de lançamento (054+).

## 16. "Uma listagem nova custa < 80 linhas" só é demonstrável na spec 036

O DoD da 030 pedia a demonstração com a listagem de tarefas — mas tarefas só ganham
modelo na 032 e listagem na 036, e o ciclo não adianta trabalho de spec futura. A infra
(`core/listing.py`, `core/export.py`, `useListPage`, `ListPageLayout`) está pronta;
a conta de linhas fica para a 036 fechar.

**Spec-alvo:** 036 (caixa de entrada) — medir e registrar no test-timing da spec.

## 17. Wall-clock do `make test` à beira do teto (119/120 s)

A suíte backend saltou de ~74 s (spec 029) para ~110 s entre as specs 031–032, com a
latência dobrada e espalhada por TODOS os testes (sem outlier no --durations) — assinatura
de contenção do host Docker compartilhado, não de regressão de código. A limpeza do
rito_test (TRUNCATE antes do pytest, spec 032) removeu o acúmulo, mas a margem ficou em
~1 s. Sintomas correlatos: flake de `StateCitySelect.test.tsx` sob carga (waitFor de 1 s
estoura a 1,9 s; isolado leva 0,24 s).

**Spec-alvo:** 040 (refatoração de Tarefas) — medir de novo e, se continuar >90 s:
aumentar o waitFor do teste flake e reavaliar o boot do app por teste — ATUALIZAÇÃO
(033): escopo de sessão/módulo NÃO funciona (pytest-asyncio loop_scope deixa conexões
asyncpg presas a loops diferentes; 151 testes quebraram na tentativa, revertida). O
caminho, se a margem voltar a apertar, é reduzir o CUSTO do boot por teste (ex.: pool
menor em APP_ENV=test), não o escopo do fixture. Na 033 a suíte voltou a 99 s.

**ATUALIZAÇÃO (040):** medido **174 s** no fechamento da spec (era 156 s na 039) —
acima dos 90 s aspirados pelo checklist da 040, ainda 42% abaixo do gate de 300 s do
CLAUDE.md. O flake de `StateCitySelect` não se manifestou nesta execução (waitFor
inalterado). O delta 156→174 vem do seed de 20 mil linhas do novo `test_inbox_perf.py`
(module-scoped, roda 1× por worker do xdist) somado à variância de contenção do host.
Decisão: o item **permanece aberto, re-atribuído à 050** (refatoração das integrações
CNJ), com o caminho já validado na 033 — reduzir o custo do boot do app por teste
(lifespan completo com engine/Redis/S3 por teste via fixture `client`), não mexer em
escopo de fixture nem em waitFor às cegas. Se a 050 não bastar, a 098 (performance)
fecha a conta com divisão da suíte em grupos paralelos por domínio.

**ATUALIZAÇÃO (050):** investigado o caminho da 033/040 — `create_engine_from_url`
(`app/core/db.py`) usa `pool_size`/`max_overflow` padrão do SQLAlchemy (5/10), mas o
pool é preenchido **sob demanda** no primeiro checkout, não na criação do engine; um
teste típico (1-2 queries) só abre 1 conexão de qualquer forma, então `pool_size`
menor não reduziria o custo real por teste — a hipótese original (registrada na 033)
não se confirmou na leitura do código. O custo por teste é dominado por
handshake TCP/auth do Postgres por engine novo (`client`/`app_session_factory` são
function-scoped, um engine por teste, sem reuso) somado à contenção do host
compartilhado (mesma causa raiz apontada desde a primeira medição, spec 032) — nenhum
dos dois se resolve mudando `pool_size`. Não mexido: o risco de tocar `client`
(fixture usada por 49 arquivos de teste) sem um ganho validado não compensa,
especialmente depois da tentativa de escopo de sessão/módulo ter quebrado 151 testes
na 033. Medido no fechamento da 050: **ver `test-timing.json`** — segue **bem abaixo**
do gate de 300 s. Item **permanece aberto, re-atribuído definitivamente à 098**
(performance) com a recomendação já mais específica: dividir a suíte em grupos
paralelos por domínio (xdist com `--dist=loadgroup` ou execução por diretório), não
mais tentar reduzir custo de boot por teste — essa via já foi auditada duas vezes
(033, 050) sem alvo real encontrado.

## 18. Cálculo de prazo fatal das intimações roteadas ainda não existe

A spec 045 (roteamento de intimação → tarefa) cria a tarefa sistêmica "Intimações
Judiciais" com `scheduled_date = availability_date` (regra 3), mas nunca calcula
`deadline_date` — o cálculo de prazo processual de verdade (contagem de dias úteis,
suspensões, tipo de prazo por classe/assunto do CNJ) é um problema em si, fora do
escopo da 045. O campo fica `NULL`, indistinguível na UI de "usuário não definiu prazo"
(qualquer tarefa manual também começa assim). Regra registrada de propósito na 050
(auditoria §4): `PostDetailPage` agora mostra "Prazo não calculado" em vez de omitir o
campo quando `task_type_name === "Intimações Judiciais"` e `deadline_date` é nulo —
resolve a ambiguidade visual sem inventar um cálculo que não existe.

**Spec-alvo:** 086 (prazo processual) — implementar o cálculo de verdade e então trocar
"Prazo não calculado" por `deadline_date` preenchido no momento do roteamento.

## 19. Fixtures HTTP do DJEN/DataJud têm dado real de pessoa identificável

Achado na auditoria de segurança da spec 050 (checklist "fixtures sem dado real,
anonimize"): `tests/fixtures/http/comunicaapi.pje.jus.br/oab_mg.json` tem um CPF real
completo (`093.026.046-59`) e vários fixtures (`oab_mg.json`, `cancelada.json`,
`trt2.json`, `tjsp.json`, `tjsp_processo.json`) têm nomes completos de partes reais —
dado capturado ao vivo da API pública do DJEN/DataJud para gravar os fixtures das
specs 042/044/046/047. Juridicamente é dado público (comunicação processual É pública
por lei), mas a prática do projeto pede anonimização mesmo assim.

**Não corrigido na 050 de propósito:** esses fixtures são consumidos por ~40 testes
espalhados de 042 a 049 (parsers, sync, roteamento, movimento) — vários fazem
asserção sobre contagem/conteúdo específico de destinatários/nomes. Trocar o
conteúdo sem uma varredura completa de quem depende de qual valor arrisca quebrar
teste "sem edição" às cegas, o oposto do que uma spec de refatoração deve fazer.

**Spec-alvo:** 098 (performance/qualidade) ou uma spec dedicada — mapear TODA
asserção que depende do conteúdo desses fixtures, trocar nomes/CPF por sintéticos
preservando forma (mesma quantidade de destinatários, mesmo formato de CPF/nome)
e reconfirmar os ~40 testes um por um.

## 20. `transactions` (spec 056) não retroalimenta as regras "em uso" de contas/categorias/centros de custo

A spec 056 criou a tabela `transactions`, que é exatamente o dado que faltava para as
regras já documentadas como pendentes nas specs 054/055:

- **Contas bancárias** (`app/domain/financial/service.py`, `BankAccountService`):
  regra 3 (saldo real = `initial_amount` + lançamentos pagos), regra 4 (fatura do
  cartão = lançamentos do ciclo em aberto), regra 6 ("conta com lançamento não pode
  ser excluída") e regra 9 (`initial_amount` imutável após o 1º lançamento) — hoje
  saldo devolve sempre `initial_amount`, exclusão é livre e `initial_amount` é
  editável sem checagem. Ver `tests/integration/test_bank_accounts.py` (docstring do
  módulo) e Descobertas da spec 055.
- **Categorias e centros de custo** (`FinancialCategoryService`/`CostCenterService`):
  regra 4/6 ("excluir em uso exige transferência") — a validação de "está em uso" é
  sempre `False` hoje, então `validated_transfer()` nunca dispara o caminho de
  reatribuição de verdade. Ver `app/domain/financial/service.py:131,187`.

Deliberadamente **não** retrofitado na própria 056: essas checagens pertencem aos
domínios de contas/categorias/centros (specs 055/054), não ao de lançamentos, e
misturar as duas coisas no mesmo ciclo violaria o escopo declarado da 056
(`transactions` + regra 11 do painel financeiro do processo). Uma
`TransactionRepository.account_is_referenced()`/`category_is_referenced()` chegou a
ser esboçada durante a 056 e foi removida de propósito por ser código sem uso
enquanto o retrofit não é feito de verdade.

**Spec-alvo:** próxima spec de refatoração (070) — implementar as 6 regras acima
(3/4/6/9 de contas, 4/6 de categorias e centros), com teste que primeiro cria um
lançamento e SÓ DEPOIS confirma que saldo/exclusão/imutabilidade mudam de
comportamento (os testes atuais de 054/055 continuam cobrindo o caminho "sem
lançamento nenhum", que segue válido).

**Atualização (spec 058):** `transactions` ganhou `is_internal` (lançamento de
controle, nunca deve contar em saldo/caixa/DRE/DFC/inadimplência — regra 1 da 058).
Quando a 070 implementar o saldo real de conta (regra 3 acima), a query TEM que
filtrar `NOT is_internal`, do mesmo jeito que `TransactionRepository.
lawsuit_financial_totals` já faz desde a 058 — registrado aqui pra não esquecer no
retrofit.
