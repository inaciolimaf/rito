# Dívida técnica consciente

> Entregável da spec 010 (refatoração da Fundação). Cada item tem uma **spec-alvo** —
> onde a dívida deve ser resolvida, não "algum dia". Se uma spec-alvo já passou e o item
> continua aqui, a próxima spec de refatoração precisa decidir: resolver agora ou
> re-atribuir com justificativa nova.

## Estado no fechamento da spec 100

A auditoria final percorreu os 20 itens. O que mudou:

| Item | Estado depois da 100 |
|---|---|
| 14 — EXPLAIN sem volume real | **Resolvido** na 098: o perfilamento noturno roda com 1,95 milhão de linhas e achou o que o banco de dev escondia (a listagem de lançamentos sem paginação nenhuma, 94 FKs sem índice, o `OR` que virava Seq Scan). |
| 17 — wall-clock à beira do teto | **Resolvido** na 098: o cap de workers do pytest era uma constante de tuning da 035, de quando o backend levava ~85 s. Hoje ele é o poste mais alto e o cap subiu para 3. |
| 19 — PII real nas fixtures | **Resolvido** na 100. Ver abaixo. |
| 3, 6, 7, 8 | Reclassificados: são lacunas de cobertura de branch defensivo, não risco. Custo de fechar > valor. |
| 4, 5, 9, 10 | Reclassificados como **produto**, não dívida técnica: são telas que ninguém especificou, não código mal feito. Entram como spec 101+ se alguém quiser as telas. |
| 11, 12, 13, 15, 16, 18, 20 | **Permanecem abertos**, com a spec-alvo re-atribuída para 101+. Nenhum é risco de segurança nem de perda de dado. |

## Estado no fechamento da spec 101

A 101 corrigiu os cinco stubs cuja dependência já tinha chegado e acertou o registro. O que
mudou:

| Item | Estado depois da 101 |
|---|---|
| 13, 20 | **Resolvidos** na 101 (Bloco A): guarda de "em uso" com 409, transferências reais e saldo bancário de verdade. |
| 15 | **Resolvido** na 101: a contagem que a própria dívida pedia deu **16** enums cruzando a fronteira (gatilho era 4). `scripts/dump_enums.py` + `tests/meta/test_enum_mirror.py`. |
| 16 | **Fechada com o número medido** (237 linhas), sem re-atribuição: a métrica estava mal formulada, não havia trabalho pendente. |
| 4, 5 | Seções atualizadas para refletir a reclassificação como **produto** que a 100 já tinha decidido na tabela acima, mas nunca aplicado ao texto. |
| 14, 17 | Seções marcadas como **resolvidas na 098** — a tabela da 100 já dizia isso; o texto não. |
| 18 | **Re-atribuída** para a 122: o alvo 086 virou *IA de intimações* e nunca tocou em prazo. |
| 21 | A dívida do `SAVEPOINT`, que passou 18 specs **sem número** — foi assim que escapou da contagem da 100. Alvo: 103. |
| 22, 23, 24, 25 | **Novos**: três itens que a 101 corrigiu ou mapeou e que nunca estiveram neste documento, mais o achado do meta-teste (`last_assigned_at`). |
| 11, 12 | Continuam abertos, alvo **102** (Bloco B do plano de corte). |

### Os três handoffs que se perderam entre specs

Registrados aqui porque nenhum deles estava em lugar nenhum — não são dívida de código, são
combinações feitas numa spec e esquecidas na seguinte. É a mesma classe de falha dos cinco
stubs, num nível acima:

| Handoff | O que foi combinado | O que aconteceu |
|---|---|---|
| 038 → 086 | Cálculo de prazo fatal (dívida 18) | A 086 foi escrita como *IA de intimações*. O prazo nunca teve dono. Re-atribuído à 122. |
| 079 → 080 | View de inbox unificada dos parceiros | A 080 fechou sem o item e ninguém registrou. É decisão de escopo com custo real, não correção — entra como linha rastreada, não como trabalho (101 §3). |
| 085 → 090 | Jornada e2e 11/25 do copiloto | Idem: a 090 fechou sem a jornada. O teto de 25 jornadas (CLAUDE.md §3) segue com folga; a jornada entra quando alguém decidir gastá-la. |

Nenhum item aberto é de segurança. O roadmap de 100 specs fecha com sete pendências
funcionais conhecidas, nomeadas e classificadas — que é o oposto de fechar com zero
pendências não medidas.

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

## 4. ~~`LoginPage` pede o UUID cru do tenant~~ — RECLASSIFICADO como produto na spec 100

Não existe endpoint público que resolva um "código do escritório"/subdomínio para o UUID
de tenant — o contrato de `/auth/login` (spec 004) não carrega esse identificador no corpo,
só o header `X-Tenant-Id`. UX correta e honesta para o estado atual do backend, mas ruim
para um produto real.

**Spec-alvo:** nenhuma. Reclassificado no fechamento da 100: é tela que ninguém especificou, não código mal feito. Volta a ter alvo no dia em que virar produto.

## 5. ~~Estado "offline" do frontend~~ — RECLASSIFICADO como produto na spec 100

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

## 9. ~~Sem página de "aceitar convite" no frontend~~ — RESOLVIDO na spec 102

`POST /api/v1/invitations/accept` existe e está testado (spec 012), mas a seção 6
("Front-end") da spec só lista `/settings/users` e `/settings/users/:id` — nenhuma rota
pública para quem recebeu o convite definir nome/senha. O fluxo é funcionalmente completo
no backend, mas ninguém consegue *usá-lo* pela UI ainda; o link do e-mail de convite (que
também não existe — sem infra de e-mail, ver regras 1-2) não tem para onde apontar.

**Spec-alvo:** a spec que trouxer a infraestrutura de e-mail (envio real de convites/reset
de senha) — as duas coisas (enviar o e-mail e ter uma página que recebe o clique)
precisam nascer juntas.

## 10. ~~`/settings/users` sem link de navegação~~ — RESOLVIDO na spec 102

`/settings` continua sendo o placeholder genérico (nenhuma spec ainda construiu uma
"home" de Configurações com sub-navegação, diferente de "Conta e assinatura" na 011, que
tinha um único sub-item e pôde redirecionar direto). `/settings/users` e
`/settings/users/:id` existem e funcionam, mas exigem digitar a URL.

**Spec-alvo:** a spec que desenhar a página-índice de Configurações (ainda sem número no
roadmap) — ela precisa linkar para `/settings/users` e para os módulos de configuração
das specs 013+.

## 11. ~~`squads` com nome único sensível a caixa/acento~~ — RESOLVIDO na spec 102

Texto original:

### `squads` é a única das 5 taxonomias simples (013-019) com nome único sensível a
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

## 12. ~~Busca textual das 5 taxonomias não ignora acento~~ — RESOLVIDO na spec 102

Texto original:

### Busca textual das 5 taxonomias simples (013-019) não ignora acento, diferente de
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

## 13. ~~`CustomerOriginService.transfer`/`delete` sem lógica real~~ — RESOLVIDO na spec 101

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

**Resolvido na 101** (regras 3-4, Bloco A): `delete()` levanta `CustomerOriginInUseError`
→ 409 e `transfer()` reatribui `customers.origin_id` de verdade, devolvendo a contagem real.
`test_excluir_nao_bloqueia_ainda` foi reescrito nos dois testes que provam o comportamento
novo (sem contato → 204; com contato → 409, e transferir libera).

## 14. ~~EXPLAIN das visões precisa ser revalidado com volume real~~ — RESOLVIDO na spec 098

A checklist da spec 030 pedia `EXPLAIN ANALYZE` nas 12 visões "sem seq scan em tabela
grande". Rodado na 030 (registro em `docs/DECISOES.md`): o banco de dev tem dezenas de
linhas — seq scan é o plano ótimo nesse volume, mesmo com `enable_seqscan=off`, então o
exercício não prova nada sobre o comportamento em produção. Os índices das colunas de
predicado existem e foram conferidos em `pg_indexes`.

**Resolvido na 098:** `make test-nightly` semeia 1,95 milhão de linhas e repete o `EXPLAIN ANALYZE` fora do orçamento de 300 s do PR. Achou o que o banco de dev escondia: a listagem de lançamentos sem paginação, 94 FKs sem índice e o `OR` que virava Seq Scan.

## 15. Enums do banco espelhados à mão em TS

`PartyPoleApi`, `LawsuitOutcome`, `ContingencyLevel` e cia. são redeclarados como union
types em `frontend/src/features/*/api.ts` — duplicação manual que pode divergir do
StrEnum do backend sem nenhum alarme. A checklist da 030 pedia espelho "sem duplicação
manual"; gerar os unions TS a partir dos StrEnum via script (`scripts/dump-enums`)
continua pendente — o volume atual (3 enums) não justificou a infra nesta refatoração.

**Spec-alvo:** quando o 4º enum de domínio cruzar a fronteira da API (regra dos 3 usos)
— provavelmente status de tarefa (032) ou tipo de lançamento (054+).

## 16. ~~"Uma listagem nova custa < 80 linhas"~~ — FECHADA na spec 101, com o número medido

O DoD da 030 pedia a demonstração com a listagem de tarefas — mas tarefas só ganham
modelo na 032 e listagem na 036, e o ciclo não adianta trabalho de spec futura. A infra
(`core/listing.py`, `core/export.py`, `useListPage`, `ListPageLayout`) está pronta;
a conta de linhas fica para a 036 fechar.

**Fechada na 101 (regra 23), com a medição em vez da promessa.** Listagem medida: times
(`frontend/src/features/squads/`), a mais recente tocada por esta leva.

| Arquivo | Linhas |
|---|---:|
| `SquadsListPage.tsx` | 165 |
| `api.ts` | 59 |
| `schema.ts` | 13 |
| **Total da listagem** | **237** |

O número **não** confirma a meta de 80 linhas — confirma que a meta estava mal formulada.
As 165 linhas da página não são scaffolding: `DataTable`, `FormModal`, `ConfirmDialog` e
`useCrudResource` já absorvem paginação, ordenação, modal, submit e erro, e o que sobra é
domínio (colunas de times, avatares com teto de 3, o form de membros). Uma listagem nova
custa pouco porque não reescreve infra, não porque cabe em 80 linhas — e contar linhas de
página nunca ia medir isso.

A dívida fecha com o número medido, como a regra 23 manda, e **sem** re-atribuição: não há
trabalho pendente, há uma métrica aposentada. O que sustenta a propriedade de verdade é o
teto de duplicação da spec 119.

**Spec-alvo original:** 036 (caixa de entrada) — medir e registrar no test-timing da spec.

## 17. ~~Wall-clock do `make test` à beira do teto~~ — RESOLVIDO na spec 098

A suíte backend saltou de ~74 s (spec 029) para ~110 s entre as specs 031–032, com a
latência dobrada e espalhada por TODOS os testes (sem outlier no --durations) — assinatura
de contenção do host Docker compartilhado, não de regressão de código. A limpeza do
rito_test (TRUNCATE antes do pytest, spec 032) removeu o acúmulo, mas a margem ficou em
~1 s. Sintomas correlatos: flake de `StateCitySelect.test.tsx` sob carga (waitFor de 1 s
estoura a 1,9 s; isolado leva 0,24 s).

**Spec-alvo original:** 040 (refatoração de Tarefas) — medir de novo e, se continuar >90 s:
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

**Spec-alvo:** 122 (prazo processual — spec própria, ainda a escrever). **Re-atribuída na
101:** o alvo anterior era a 086, que foi escrita como *IA de intimações* e nunca tocou em
prazo — o handoff 038→086 se perdeu na renomeação da spec, e o item ficou apontando para
uma spec concluída que não o resolveu. Contagem de dias úteis por classe/assunto do CNJ é
um problema em si, não um stub esquecido: a 101 renomeia o destinatário (Bloco E) e
deliberadamente **não** implementa (§3, Fora de escopo). Entra junto o seed de feriados de
2031 em diante (spec 038).

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

### ✅ RESOLVIDO na spec 100

A varredura que a 050 pediu foi feita, e o receio dela não se confirmou: **nenhum teste
afirma sobre um nome ou CPF específico**. As asserções são sobre contagem, estrutura e
roteamento — a forma do dado, não o conteúdo. Trocar valores preservando a forma era,
portanto, seguro.

55 nomes de pessoa e o CPF completo foram substituídos por sintéticos, de forma
determinística e consistente entre arquivos (o mesmo nome real vira sempre o mesmo
falso, para as referências cruzadas entre a lista de partes e a citação no corpo do
texto continuarem batendo). Razão social de pessoa jurídica ficou como estava — não é
dado pessoal, e os testes que distinguem parte física de jurídica precisam da distinção.

Duas coisas que só apareceram fazendo:

- **`nome` nem sempre é nome de gente.** No DataJud o mesmo campo nomeia movimento
  processual, e a primeira passada transformou "Disponibilização no Diário da Justiça
  Eletrônico" em "ANA SILVA". O discriminante é a CAIXA ALTA: registro de tribunal
  escreve nome de pessoa toda em maiúscula, descrição de movimento em caixa mista.
- **Dado real tem erro de digitação.** "CARLOS HENRIQUE BEREGENO" aparece no campo
  estruturado e "CARLOS HENRIQE BEREGENO" (sem o U) no corpo do texto — o próprio
  tribunal digitou errado. A troca por campo estruturado não alcança a variante, e ela
  sobreviveu à primeira passada.

`tests/meta/test_final_audit.py::test_nenhuma_fixture_tem_cpf_ou_cnpj_de_pessoa_real`
impede a volta: qualquer CPF ou CNPJ que não seja o sintético de teste falha o CI.

## 20. ~~`transactions` não retroalimenta as regras "em uso" de contas/categorias/centros~~ — RESOLVIDO na spec 101

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

**Resolvido na 101** (regras 7-12, Bloco A): as 6 regras existem e têm teste. O saldo é
`initial_amount` + pagos (`NOT is_internal`, regra 1 da 058), cartão devolve a fatura do
ciclo reaproveitando `card_invoice` (059), exclusão em uso devolve 409 nos três domínios,
`initial_amount` trava depois do 1º lançamento e as transferências reatribuem de verdade.
O `account_is_referenced()`/`category_is_referenced()` que a 056 removeu por ser código sem
uso voltou como `count_references`/`reassign_references` em `app/core/transfer.py` — uma vez
só, compartilhado pelos quatro domínios (regra dos 3 usos, CLAUDE.md §6).

**Spec-alvo original:** próxima spec de refatoração (070) — implementar as 6 regras acima
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

---

## 21. Cancelamento no meio do nó derruba a sessão (spec 082 + 090)

**Descoberto em:** spec 092, no teste de contrato dos grafos (`test_graph_contract.py`).

O `GraphRuntime` diz, em comentário e em intenção, que o cancelamento acontece **entre
nós** (regra 6 da 082) — "nunca no meio de um nó, que poderia estar com uma escrita em
andamento". Mas o **timeout por nó** (regra 5) é implementado com
`asyncio.wait_for(iterator.__anext__(), timeout=...)`, e `wait_for` cancela exatamente no
meio: onde a corrotina estiver.

Enquanto o primeiro `await` dentro do nó era a chamada ao modelo, isso não fazia mal. A
spec 090 acrescentou duas consultas antes dela (a configuração da feature e o teto de
gasto), e um timeout curto passou a poder cortar **dentro de uma query**. Cancelar uma
query em andamento deixa a sessão do SQLAlchemy inutilizável, e aí o próprio caminho de
`_fail` — que existe para registrar o timeout — falha com `PendingRollbackError`. O
resultado prático é o pior possível: a execução que estourou o tempo não consegue
registrar que estourou o tempo.

**Contorno atual:** o teste de contrato usa `node_timeout_s=1.0`, folgado o bastante para
que o corte caia na chamada ao modelo e não numa query. Em produção o timeout é de
dezenas de segundos, então o caso é raro — mas raro não é nunca, e é o tipo de falha que
aparece no dia em que o banco está lento, que é justamente o dia em que os timeouts
disparam.

**Correção de verdade:** envolver o avanço do nó num `SAVEPOINT`
(`session.begin_nested()`), como já fazem `AiActionService.approve` (084) e
`AutomationEngine.advance` (092), para que o rollback do cancelamento devolva a sessão
utilizável e o registro da falha sobreviva. Não foi feito em 091–093 porque mexe na
semântica de checkpoint do runtime da 082 e merece o seu próprio ciclo, com os testes de
082 rodando junto.

**Spec-alvo:** 103 (Bloco D do plano de corte da 101).

**Numerada na 101 (Bloco E).** Este item passou 18 specs sem número, e foi exatamente
assim que escapou do fechamento da 100: a tabela de encerramento daquela spec contava
itens **numerados**, e um item sem número não aparece numa contagem de itens numerados.
O meta-teste `test_toda_divida_aberta_tem_numero_e_alvo_no_futuro` existe por causa dele.


## 22. ~~`StageService.transfer`/`delete` sem lógica real~~ — RESOLVIDO na spec 101

Gêmeo exato do item 13, e **nunca esteve neste documento**: o próprio item 13 citava o caso
das etapas e o classificava como "ainda genuinamente bloqueado — `lawsuits.stage_id` só
chega na spec 022". A 022 chegou 78 specs antes da 101, e a classificação nunca foi
revisitada. Enquanto isso, excluir uma etapa em uso estourava `IntegrityError` não tratado
→ 500.

Registrado aqui porque o valor do registro não é listar o que está aberto — é impedir que
um item saia da lista por engano. É o buraco que o meta-teste
`test_nenhum_comentario_adia_para_spec_ja_concluida` fecha na origem.

**Resolvido na 101** (regras 1-2, Bloco A).

## 23. ~~Contatos com processo ativo: filtro e contadores eram stub~~ — RESOLVIDO na spec 101

Também **nunca esteve neste documento**. `GET /customers?has_active_lawsuit=true` casava
com `Customer.id == uuid.uuid4()` — uma condição escrita para nunca ser verdadeira — e os
contadores `with_active_lawsuit`/`without_active_lawsuit` do dashboard eram as constantes
`0` e `total`. `lawsuit_parties` existe desde a spec 023.

O dashboard publicava um número constante como se fosse medição. Nenhum teste falhava,
porque os testes existentes verificavam o stub.

**Resolvido na 101** (regras 5-6, Bloco A).

## 24. ~~Rota `/settings` não existe~~ — RESOLVIDO na spec 102

`navItems.ts` aponta para `/settings` desde a spec 008. A rota nunca foi declarada em
`App.tsx`: clicar em "Configurações" leva ao `NotFoundPage`.

Sobreviveu 92 specs porque as duas coisas que deveriam ter pego olhavam para o lado errado:
`Sidebar.test.tsx` percorre `NAV_ITEMS` só para conferir que o link **renderiza**, e a
jornada e2e "navegar por todos os módulos" itera uma **cópia manual** da lista, que omite
justamente Financeiro, Configurações e Conta e assinatura.

**Spec-alvo:** 102 (Bloco C do plano de corte da 101) — criar o hub de configurações, a
tela `/accept-invite` (item 9) e o meta-teste que deriva as rotas de `NAV_ITEMS` em vez de
copiá-las.

## 25. `TaskTypeResponse.last_assigned_at` é sempre `None`

`app/domain/task_types/router.py:52` devolve `last_assigned_at=None` fixo. A regra 9 da
spec 031 descreve o campo como "derivado, nunca armazenado" — derivado de `posts`, que
existem desde a spec 032. O cálculo nunca foi escrito.

Encontrado na 101 pelo meta-teste `test_nenhum_comentario_adia_para_spec_ja_concluida`
(o comentário no schema dizia "None até a spec 032"), e deliberadamente **não** resolvido:
não é um dos cinco stubs do escopo da 101 (§3 — "fora de escopo é vinculante"). O achado
vale como prova de que o meta-teste funciona em caso que ninguém tinha mapeado.

**Spec-alvo:** 123 — calcular sobre `posts` ou remover o campo do contrato. Devolver um
campo sempre nulo é pior que não ter o campo: o front não distingue "nunca atribuído" de
"não calculado".


## 26. "Atividades" não tem tela de listagem

`navItems.ts` aponta "Atividades" para `/posts` desde a spec 008, e a rota nunca existiu —
o item caía no `NotFoundPage`, exatamente como o `/settings` (item 24). Achado pelo
meta-teste `test_toda_rota_do_menu_lateral_existe_em_app_tsx` **no mesmo ciclo em que ele
foi escrito**, num caso que nenhuma das 100 specs tinha mapeado.

Diferente do 24, aqui não faltava só a rota: a **tela** não existe. Só há
`PostDetailPage` (`/posts/:id`); a listagem de atividades — com filtros, seleção em massa
e export, como as outras listagens do CLAUDE.md §6 — nunca foi especificada.

**Contorno na 102:** `/posts` redireciona para `/home` (o painel de tarefas), mesmo padrão
do atalho `/goals` da spec 028. O usuário deixa de cair num 404 e vai para o lugar mais
próximo do que pediu. O que **não** foi feito, de propósito, é silenciar o meta-teste com
uma lista de exceções: um gate que aceita exceção por arquivo deixa de morder (é o alerta
que a própria spec 110 registra).

**Spec-alvo:** 124 — a listagem de atividades como tela própria, reaproveitando
`DataTable`/`FilterBar`/`useListPage`. Enquanto ela não existir, o redirect fica.
