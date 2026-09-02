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

## 21. ~~Cancelamento no meio do nó derruba a sessão~~ — RESOLVIDO na spec 103

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

**Correção proposta (INVALIDADA — ver abaixo):** envolver o avanço do nó num `SAVEPOINT`
(`session.begin_nested()`), como já fazem `AiActionService.approve` (084) e
`AutomationEngine.advance` (092), para que o rollback do cancelamento devolva a sessão
utilizável e o registro da falha sobreviva.

### O SAVEPOINT não resolve — medido na tentativa da spec 103

A spec 103 foi aberta para aplicar exatamente esse remédio, e ele **não funciona**. Três
medições, nesta ordem:

1. **`ROLLBACK TO SAVEPOINT` roda sem erro e não adianta.** Quando o `asyncio.wait_for`
   cancela com uma query em voo, o asyncpg invalida a **conexão**, não só a transação. O
   rollback do savepoint retorna OK e a próxima instrução na mesma sessão ainda levanta
   `PendingRollbackError: Can't reconnect until invalid transaction is rolled back`. O
   savepoint resolve a falha que nasce NO BANCO (constraint, FK) — que é o caso de 084 e
   092 — e esta não é dessa família.

2. **Só um `session.rollback()` completo reconecta** — e ele leva junto tudo o que a
   transação escreveu, inclusive os passos já registrados da execução.

3. **O runtime não pode dar esse rollback.** Quem abre a transação é o chamador:
   `get_session_for_current_user` faz `async with session_factory() as session,
   session.begin()`, e a rota inteira roda dentro dela. Um `rollback()` de dentro do
   runtime quebra o contexto de quem chamou
   (`InvalidRequestError: Can't operate on closed transaction inside context manager`).
   Pior no `POST /ai/threads` com `autorun=true`, onde o thread é **criado e executado na
   mesma transação**: o rollback apagaria a própria linha que o `_fail` precisa atualizar.

**O que a correção de verdade exige.** Não é uma linha; é uma decisão sobre quem é dono da
transação no runtime. Os caminhos viáveis, em ordem de preferência:

- **Mover o timeout para a fronteira de I/O que é segura de cancelar** — a chamada HTTP ao
  modelo, dentro do `AiRunner` — em vez do avanço do nó, que pode estar segurando uma
  conexão do banco. Isso honra a regra 6 da 082 ("cancelamento entre nós") de verdade, em
  vez de prometê-la e violá-la com `wait_for`.
- **Sessão própria para a escrita de bookkeeping** (passos, status), independente da
  transação da requisição, para que o registro da falha nunca dependa da sessão envenenada.
- **Commit por passo**, que também resolveria a perda do histórico do item 2.

Qualquer um dos três muda a semântica de transação do runtime da 082 e precisa dos testes
dela rodando junto — é o ciclo próprio que a dívida sempre pediu, agora com o beco sem
saída já mapeado.

**Reprodução guardada:** um nó que faz `SELECT pg_sleep(3)` na sessão do runtime, com
`node_timeout_s=0.3`, levanta `PendingRollbackError` dentro do `_fail`.

### Resolvido na spec 103 — o segundo caminho da lista acima

A reprodução guardada virou teste (`tests/integration/test_ai_runtime_timeout.py`), e a
decisão sobre quem é dono da transação foi tomada assim:

1. **O registro da falha tem sessão própria.** `GraphRuntime._fail` tenta escrever pela
   sessão de quem chamou, como sempre; se essa escrita levantar `SQLAlchemyError` — o
   sintoma de a conexão ter morrido —, o passo de erro, o checkpoint e o `status = error`
   vão por uma `AsyncSession` que o runtime abre, usa, **comita** e fecha. Sozinha, essa
   escrita não depende de um commit que já não vai acontecer.
2. **Quem vai rodar existe antes de rodar.** Uma conexão nova não enxerga linha não
   comitada, então o `POST /ai/threads?autorun=true` e a conversa nova do copiloto
   passaram a criar o thread numa transação própria (`create_durable_thread`), que
   commita antes de a execução começar. Era este o caso que a análise acima classificou
   como o pior.
3. **A requisição morre, e diz que morreu.** O runtime levanta `RuntimeSessionLostError`
   em vez de devolver um `GraphResult` como se nada tivesse acontecido: a transação da
   requisição morreu de verdade e ninguém além de quem a abriu pode dar o `rollback`. As
   rotas traduzem em **503**; no SSE, onde a resposta já começou, vira um evento `error`
   seguido do `rollback` explícito de quem abriu a transação.

O caminho 1 da lista de preferências (mover o timeout para a fronteira de I/O) **não** foi
escolhido: o `test_hangs` da 082 é um nó que trava sem tocar em banco nem em modelo, e sem
o `wait_for` genérico ele voltaria a pendurar a execução para sempre. O watchdog continua
onde estava; o que mudou é que o registro da falha não depende mais da vítima dele.

O resíduo — os passos anteriores ao timeout somem no `rollback` da requisição — está
numerado como o item **27**, e é ele que o "commit por passo" da lista acima resolve.

**Spec-alvo:** 103 (Bloco D do plano de corte da 101) — entregue.

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


## 27. Passo já registrado some quando o timeout mata a sessão da requisição

Resíduo declarado da spec 103. Com o registro fora de banda, uma execução que estoura o
tempo dentro de uma query grava o passo de erro e termina em `error` — mas os passos
**anteriores**, que foram escritos na transação da requisição, vão embora com o `rollback`
que essa transação leva.

O efeito visível é um buraco na numeração: `ai_steps` fica com um único passo de erro
numerado 3, e os passos 1 e 2 não existem. Quem audita vê o fim sem o meio.

Não é perda de dado do escritório (nada do domínio é escrito por esses passos, que são o
registro da própria execução), e é estritamente melhor que o estado anterior à 103, em que
não sobrava nem o passo de erro. Mas é uma meia-verdade guardada no banco, e o
`ai_checkpoints` existe justamente para "retomar de onde parou": um checkpoint que só vale
se a requisição inteira der certo não é um checkpoint.

**Correção:** commit por passo — o terceiro caminho da lista do item 21. O `_record_step`
deixa de escrever na transação de quem chamou e passa a ter a mesma sessão própria que o
registro da falha já tem, comitando a cada nó. É mudança de semântica de transação do
runtime da 082 (o `_ensure_not_cancelled` lê o status do thread pela sessão da requisição,
e o teste de cancelamento da 082 depende disso), então precisa dos testes da 082 rodando
junto e de um ciclo próprio.

**Spec-alvo:** 125 — commit por passo no runtime de agentes.


## 28. `TemplateEditor.test.tsx` é intermitente e faz o gate mentir

Achado no ciclo da spec 104, que não toca uma linha de front-end. O teste
`frontend/src/features/templates/TemplateEditor.test.tsx` ("aplica negrito pela toolbar")
falhou **quatro execuções seguidas** por estourar o `testTimeout` padrão do Vitest (5 s) e
em seguida passou em **325 ms**, com o mesmo código e a mesma máquina. A diferença é
aquecimento: o primeiro `render` do tiptap num host frio (transform, JIT, cache do Vite)
passa dos 5 s; morno, ele custa centésimos.

O que o torna dívida e não só chateação: as três suítes têm um **gate de wall-clock**
(CLAUDE.md §3, §11), e um teste que falha por lentidão de aquecimento faz o gate mentir
nos dois sentidos — reprova um PR correto num host frio, e ninguém aprende nada quando
passa. A regra "nunca `sleep` em teste, use espera por condição" já está sendo seguida
aqui (`waitFor` com teto próprio de 3 s); o que estoura é o teto do teste inteiro, que
inclui a montagem.

**Correção provável:** separar a montagem do editor da interação (montar num
`beforeEach`, ou aquecer o módulo uma vez por arquivo) para que o teto de 5 s meça o que
o teste quer medir. Subir o `testTimeout` do arquivo é o contorno preguiçoso: esconde o
sintoma e o próximo host mais frio o traz de volta.

**Spec-alvo:** 110 — a refatoração cujo objeto é exatamente gate que deixou de morder.

---

## 29. A trava do preparo do template é solta antes de proteger qualquer coisa

Achada no ciclo da spec 117, ao rodar a suíte com um template exclusivo — que é
exatamente o que o `docs/PLANO-ONDAS-106-121.md` §2.2 manda um agente fazer para não
colidir com outro.

`tests/conftest.py:96` toma a trava e `tests/conftest.py:113` a devolve:

```python
_psql(maintenance_url, f"SELECT pg_advisory_lock({_TEMPLATE_LOCK_KEY})")
try:
    ...
finally:
    _psql(maintenance_url, f"SELECT pg_advisory_unlock({_TEMPLATE_LOCK_KEY})")
```

Só que `_psql` (`conftest.py:59-64`) abre uma conexão asyncpg e a **fecha no `finally`**.
`pg_advisory_lock` é trava de **sessão**: ela morre junto com a conexão. Ou seja, a trava
é solta no instante seguinte ao ser tomada, e o `pg_advisory_unlock` roda numa conexão
nova que não detém trava nenhuma — o Postgres responde `false` e emite warning, que
ninguém lê porque o retorno é descartado.

**Por que ninguém viu em 100 specs:** no caminho normal, `scripts/run-tests.sh` roda
`alembic upgrade head` sobre o template *antes* de o pytest subir. Quando os 12 workers do
`-n auto` chegam em `_preparar_template`, `_template_esta_pronto()` devolve `True` para
todos e ninguém entra no bloco protegido. A trava quebrada nunca é exercitada.

**Quando morde:** template novo, sem o `alembic upgrade` prévio. Os 12 workers entram
juntos no bloco, todos fazem `DROP DATABASE` / `CREATE DATABASE` e disparam 12 `alembic
upgrade head` concorrentes sobre o mesmo banco. O sintoma é `UniqueViolationError` em
migration, e a suíte inteira cai antes do primeiro teste.

**Correção:** a trava precisa viver na mesma conexão que o trabalho que ela protege — uma
conexão aberta em `_preparar_template` e mantida do `pg_advisory_lock` até o
`pg_advisory_unlock`, com `_psql` usada só para o resto. Alternativa mais simples e talvez
melhor: `pg_advisory_lock` numa conexão própria mantida viva pelo escopo do `with`.

**Spec-alvo:** 110 — é auditoria da 105, e este é o caso exemplar de gate que só parece
funcionar porque o caminho que o exercita nunca é tomado.

---

## 30. ~~A suíte backend fica vermelha depois das 21h de Brasília~~ — RESOLVIDO na spec 114

Medida no ciclo da spec 117: rodando às 22h13 locais (01h13 UTC do dia seguinte), **12
testes falham** por fronteira de data. Confirmado de novo às 22h25 locais.

A causa é a dívida que a spec 114 vai pagar: 94 chamadas a `date.today()` leem o relógio
do **processo**, que em UTC já virou o dia. Um teste que semeia "vence hoje" com data
local e afirma "não está vencido" recebe do servidor um "hoje" que é amanhã.

O que torna isto dívida por si só, e não só um sintoma da 114: **o gate de wall-clock e o
gate de query budget rodam sobre uma suíte que não é determinística no tempo**. Um PR
aberto à noite reprova; o mesmo PR reprovado passa de manhã sem uma linha mudar. Isso
treina todo mundo a reexecutar CI em vez de ler falha — que é o mesmo estrago da dívida 28,
por outro caminho.

**Correção:** é a spec 114 inteira (`core/clock.py` injetado por `Depends`). O que esta
dívida acrescenta é a **prioridade**: enquanto ela não fecha, qualquer medição noturna da
suíte — cobertura, wall-clock, orçamento de query — sai errada para baixo, e ninguém sabe
disso ao ler o número.

### ✅ RESOLVIDO na spec 114

As 12 falhas sumiram. Mas fechá-la exigiu mais do que trocar `date.today()`: cinco pontos
liam `datetime.now(UTC).date()`, que o `DTZ` **não** pega — tem fuso, só que o errado.
Eram a janela de busca do DJEN (`monitored_terms/sync.py`), os prazos do motor de
automações (`automations/{engine,actions,decision}.py`) e quatro arquivos de teste que
derivavam `_TODAY` de `_NOW.date()`.

A lição que fica para a 120: **`DTZ` verde não significa «sem bug de fuso»**. Ele pega
`date.today()` e `datetime.now()` sem `tz`; não pega quem converte para o fuso errado de
propósito ou por descuido. O meta-teste `test_nenhum_date_today_em_app` tem a mesma
limitação, por construção.

O que sobrou dessa família virou a **dívida 32**.

---

## 31. `func.now()` é constante dentro de um teste, e ordenação por data virou cara ou coroa

Achada no ciclo da spec 114, ao investigar uma falha que parecia regressão e não era:
`tests/integration/test_customers_listing.py::test_ordenacao_por_created_at_desc_por_padrao`
falha **3 em 6 execuções no HEAD limpo**, sem uma linha alterada.

O mecanismo não é lentidão nem concorrência. `created_at` é
`mapped_column(server_default=func.now())` (`app/core/models.py:32`), e no PostgreSQL
`now()` devolve **o instante de início da transação**, não o do statement. A spec 105
passou a rodar cada teste dentro de uma única transação, com as sessões entrando nela por
`SAVEPOINT` — então **todas as linhas criadas dentro de um mesmo teste nascem com o
mesmo `created_at`**, por mais requisições HTTP separadas que as tenham criado.

Com o valor de ordenação empatado, `paginate_keyset` desempata por `Customer.id`, que é
UUID v4. O resultado do teste passa a depender de qual UUID aleatório saiu maior: uma
moeda, jogada a cada execução.

**Por que isso é pior que um teste chato:** o teste afirma uma regra real do contrato de
listagem do `CLAUDE.md` §6 (keyset, ordenação estável), e hoje ele dá o veredito certo por
acaso em metade das vezes. Um PR que quebrasse a ordenação de verdade teria 50% de chance
de passar. É a dívida 28 de novo — gate que mente —, por um caminho diferente e mais
silencioso.

**Escopo real, ainda não medido:** qualquer teste que dependa de `created_at` distinto
entre linhas criadas no mesmo teste está sujeito ao mesmo empate. O levantamento faz parte
da correção.

**Correções possíveis, em ordem de preferência:**
1. O teste passa a controlar `created_at` explicitamente, em vez de depender do relógio do
   banco — é o mesmo princípio que a spec 114 aplica ao «hoje»: quem afirma sobre tempo
   injeta o tempo.
2. `statement_timestamp()` em vez de `now()` no `server_default` — resolve a raiz, mas
   muda comportamento de produção e precisa de migration, então é decisão própria.
3. Desempate por algo determinístico no teste (nome), o que enfraquece o que ele afirma.

**Spec-alvo:** 110 — auditoria da 105, que é de onde o efeito colateral veio.

### Parcialmente atacada na spec 106 — a causa raiz CONTINUA

O teste de ordenação de contatos foi corrigido no ciclo do degrau 1 da 106, porque ele
reprovava o `make test` em metade das execuções e travava o gate. A correção foi a opção 1
da lista acima: **o teste passou a escrever os `created_at` que afirma**, em vez de
depender do relógio do banco — mesmo princípio da spec 114, quem afirma sobre tempo injeta
o tempo. Cinco execuções seguidas verdes, contra ~50% antes.

**Isso não fecha a dívida.** O que foi corrigido é uma manifestação; o mecanismo continua
inteiro: `func.now()` segue devolvendo o instante de início da transação, a transação
segue sendo uma só por teste (spec 105), e **qualquer outro teste que dependa de
`created_at` distinto entre linhas criadas no mesmo teste continua sujeito ao mesmo
empate** — só ainda não deu azar. O levantamento de quais são esses testes segue sendo
trabalho da correção, e é a parte que ninguém fez.


---

## 32. Timestamp em UTC comparado com data de escritório

Achada ao fechar a spec 114, que resolveu «que dia é hoje» mas não esta: há três lugares
onde um **timestamp gravado em UTC** é comparado com uma **data pensada no fuso do
escritório**, e os dois discordam nas horas em que o dia UTC já virou e o do escritório
não.

**1. Relatórios que filtram por `created_at`.** `new_customers` e `new_lawsuits`
(`reports/tabular_repository.py`) recebem `from`/`to` como datas e comparam com
`created_at`, que é `timestamp` UTC. Um contato cadastrado às 23:47 em São Paulo tem
`created_at` no dia seguinte em UTC e **some** do filtro «de hoje até hoje».

**2. Tempo total de processo.** O mesmo relatório calcula `closure_date - created_at`, e
com `closure_date` no dia do escritório e `created_at` em UTC o resultado pode sair
**negativo** — foi assim que a dívida apareceu (`assert -1 == 0`).

**3. O CHECK `ck_tx_payment_not_future`.** Ele vive no banco e compara com
`CURRENT_DATE`, que é o dia do servidor. Depois da 114 a aplicação recusa em fuso do
escritório e o banco em UTC: por três horas por dia os dois discordam. Hoje isso não
quebra escrita nenhuma — a aplicação é a mais restritiva das duas, então ela recusa antes
—, mas são duas regras com o mesmo nome e respostas diferentes, e a próxima pessoa a
mexer vai assumir que concordam.

**Contorno em vigor:** os testes afetados falam explicitamente o relógio do banco
(`_HOJE_UTC` em `test_reports_tabular.py`, `datetime.now(UTC).date()` em
`test_transactions.py`), com comentário citando esta dívida. Eles documentam o
comportamento atual em vez de escondê-lo.

**Correção:** converter o timestamp para o fuso da conta na própria query
(`created_at AT TIME ZONE ...`) antes de comparar com data, e decidir se o CHECK do banco
deve sair ou virar uma regra que aceita o fuso. As duas mexem em SQL — a segunda pede
migration —, e é por isso que ficaram fora da 114, cujo §5 declara «nenhuma migration».

**Spec-alvo:** própria, a definir. A 120 deve pautá-la ao revisar o que o gate de `DTZ`
não alcança.

---

## 33. Uma jornada e2e falha quando as três suítes disputam CPU

Observada uma vez, ao fechar a spec 114: no primeiro `make test` com as portas livres, a
jornada 6/25 (`schedule.spec.ts` — criar compromisso na agenda) falhou ao não achar a
opção do cliente no `EntityPicker`; nas duas execuções seguintes ela passou, e o e2e
fechou 10/10.

O que distingue as execuções não é o código: é a **carga**. O `make test` roda as três
suítes concorrentes (CLAUDE.md §3), e o Playwright ainda usa `workers: undefined` fora do
CI — ou seja, um worker por núcleo, competindo com o `pytest -n auto` e o Vitest pelos
mesmos 12 núcleos. O seletor esperou 5 s por uma opção que a máquina ocupada demorou mais
que isso para renderizar.

**Uma observação só**, e é por isso que isto entra como dívida e não como correção: pode
ser um caso isolado ou pode ser o começo de um gate que só passa em máquina folgada — que
é o estrago das dívidas 28 e 31 por um terceiro caminho. O que fica registrado é o sinal e
como reconhecê-lo: se voltar, **não reexecute até dar sorte**.

**Correção provável:** limitar `workers` do Playwright também fora do CI, para o e2e não
disputar núcleo com as outras duas suítes; ou dar ao seletor de entidade uma espera por
condição com teto próprio, em vez do teto padrão de 5 s.

**Segunda ocorrência, no degrau 2 da spec 106.** O `make test` reprovou com as três
suítes passando individualmente logo em seguida — backend 1.574, frontend 313, e2e 10/10 —
e a execução seguinte fechou verde com `EXIT=0`. **Não foi possível dizer qual perna caiu:**
o log capturado em segundo plano guardou só a cauda, e o marcador `--- <suíte> FALHOU ---`
do `scripts/run-tests.sh` ficou na parte truncada.

Isso acrescenta um pedaço à dívida: além do gate falhar sob carga, **o diagnóstico da falha
se perde**. Quem reprovar no CI vai olhar para o mesmo buraco. Vale considerar, junto da
correção, que o `run-tests.sh` repita ao final quais suítes falharam — hoje ele só diz o
wall-clock e devolve o código de saída.

**Terceira ocorrência, ao fechar o degrau 3 da spec 106 — e a pior.** Não uma jornada:
**cinco**, na mesma execução (contatos, financeiro, caixa de entrada, publicações e
agenda). Todas no mesmo ponto: preencher a busca do `EntityPicker` e não achar a opção. A
execução seguinte, com a **árvore de trabalho idêntica**, fechou 10/10 em 140 s de
wall-clock contra os 169 s da que falhou; a jornada 3/25 rodada sozinha passa em 2,6 s.

Isso muda a leitura da dívida em dois pontos:

1. **Não é uma jornada frágil, é um padrão.** As cinco que caem são exatamente as cinco
   que passam por um `EntityPicker`; as cinco que passam não usam nenhum. O defeito não
   está espalhado — está concentrado na espera do seletor assíncrono, e isso torna a
   segunda correção provável (teto de espera próprio para o `EntityPicker`) mais
   promissora que a primeira.
2. **A escala não é estável.** Uma ocorrência, depois uma, agora cinco. Um gate que
   reprova 5 de 10 jornadas por carga não é um flake tolerável: é um gate que vai ser
   ignorado na terceira vez que reprovar sem motivo, e aí ele deixou de existir.

O wall-clock maior na execução que falhou (169 s contra 140 s) é a confirmação direta da
hipótese de carga — a máquina estava mais lenta nas duas pontas ao mesmo tempo.

**Quarta ocorrência (spec 112) — e agora o gate de wall-clock também caiu.** O `make test`
reprovou com **434 s** contra o orçamento de 300 s, mais uma jornada e2e (a 4/25, que passa
por um `EntityPicker`, como as outras). A execução seguinte, mesma árvore, fechou em
**140 s**. Três vezes mais lento, sem uma linha de diferença.

A perna que estourou não foi o e2e: foi o **backend**, com 283 s contra os ~92 s habituais.
E a causa foi encontrada desta vez: `uptime` acusava load average entre 4,7 e 6,3, com uma
**segunda sessão do Claude Code rodando em outro projeto do usuário** e o Chrome com
renderizadores a 90-99% de CPU. Carga externa à suíte, na mesma máquina.

Isso acrescenta uma dimensão que as três ocorrências anteriores não tinham: **o gate de
orçamento do §11 mede uma coisa que não depende só do projeto**. Um número que varia 3× por
causa de quem mais está usando a máquina não separa «o projeto ficou lento» de «o laptop
estava ocupado» — e a primeira vez que ele reprovar sem motivo real, alguém aumenta o teto.

Duas correções possíveis, para a spec que atacar isto:

1. **Medir CPU consumida em vez de tempo de parede** (`os.times()`, `time.process_time()` ou
   `/usr/bin/time`), ou normalizar o wall-clock pela carga observada. Tempo de CPU é
   praticamente imune a vizinho barulhento.
2. **Reprovar só na segunda medição consecutiva acima do teto.** Um estouro isolado vira
   aviso; dois seguidos viram falha. Mantém o gate honesto sem torná-lo folclore.

**Spec-alvo:** 110 ou 120 — a auditoria que perguntar se os gates ainda mordem pelo motivo
certo. Com a terceira ocorrência isto já passava de «observar» para «corrigir»; com a
quarta, são DUAS correções: o `EntityPicker` e a medição do orçamento.

---

## 34. `GET /api/public/v1/customers/birthdays` não filtra aniversariantes

**Bug de comportamento, não dívida de forma.** Encontrado ao ler `customers/repository.py`
para a spec 116; anterior a toda a leva 106–116 (conferido em `da213af`, antes da 106 — a
lógica era a mesma, escrita como `if/elif`).

A rota pública monta o filtro assim (`app/public/router.py`):

```python
alvo = month or Clock(...).today().month
items, total = await CustomerRepository(session).list_filtered(
    today=..., birthdays=f"month:{alvo}", limit=1000,
)
```

E o filtro só reconhece dois valores exatos (`app/domain/customers/repository.py`):

```python
def _filtro_de_aniversario(birthdays: str | None, today: date) -> list[ColumnElement[bool]]:
    if birthdays not in ("day", "month"):
        return []
```

`"month:3"` não é `"month"`. O filtro devolve lista vazia, e a rota responde **os primeiros
1.000 contatos do escritório** — não os aniversariantes.

São dois defeitos empilhados:

1. **O filtro nunca é aplicado**, pelo descasamento acima.
2. **O parâmetro `month` é decorativo.** Mesmo que o valor casasse, `_filtro_de_aniversario`
   compara com `today.month`, não com o mês pedido. Pedir dezembro em setembro devolveria
   os aniversariantes de setembro.

Não é vazamento entre escritórios — o RLS continua valendo e o escopo `read:customers` é o
mesmo. É resposta errada: quem integra pelo endpoint «aniversariantes do mês» para disparar
mensagem de parabéns manda parabéns para o escritório inteiro.

**Por que passou:** o `/api/v1/customers/birthdays` interno é testado com `scope=day|month` e
funciona. O público só tem o teste de contrato (`test_public_api_contract.py`), que confere
que a rota EXISTE e responde — nunca que ela filtra. Rota testada por existência é rota não
testada.

**Não corrigido na 116 de propósito:** a 116 é refatoração, e corrigir isto muda
comportamento. A 116 fez a incompatibilidade ficar VISÍVEL — o `CustomerQuery` do repositório
tem `birthdays: str | None` justamente porque o `CustomerFilters` da API
(`Literal["day","month"] | None`) não consegue expressar o `"month:3"` que a rota pública
manda. O tipo agora denuncia o descasamento que o `str` escondia.

**Correção:** dar ao repositório um filtro de aniversário que aceite mês explícito
(`_filtro_de_aniversario(escopo, mes, today)`), fazer a rota pública passar `alvo`, e cobrir
as duas rotas com teste que crie um aniversariante e um não-aniversariante e afirme que só o
primeiro volta.

**Spec-alvo:** spec própria de correção, não uma de refatoração. Prioridade alta: é resposta
errada em endpoint público documentado.

---

## 35. Um teste de caos só passa dependendo de quem roda junto

`tests/integration/test_resilience_chaos.py::test_datajud_ganha_historico_de_execucao_sucesso_e_erro`
passa sozinho (2,5 s), passa na suíte completa, e **falha** neste recorte:

```
pytest tests/ -k "cache or migration or observability or automation or crm or comment or chaos or guardrail"
```

O erro é `HttpRequestError: falha de transporte ... timeout simulado` escapando em vez de
ser tratado — o teste simula UM timeout e espera que a resiliência da spec 041 absorva.

Reproduzido no HEAD limpo (`git stash`), então é anterior à spec 113 e independe dela.
Nenhum par de módulos reproduz: `chaos` com `automation`, `cache`, `migration`, `crm`,
`comment`, `guardrail` ou `observability`, dois a dois, passa. Só a combinação maior falha.

**O que isso significa:** existe estado compartilhado entre testes que a transação por teste
da spec 105 não desfaz — os candidatos naturais são o **circuit breaker por host** (dicionário
de instância, mas o cliente pode estar sendo reusado) e o **token bucket de rate limit no
Redis**, que é global entre workers por construção (spec 041, regra 4) e não participa do
`ROLLBACK`. Se um teste anterior abriu o circuito do host do DataJud ou gastou a janela do
rate limit, o próximo recebe a recusa antes de tocar o transporte, e a simulação de timeout
nunca acontece como o teste espera.

**Por que não foi corrigido aqui:** a 113 é remoção de comentário morto; investigar
isolamento de teste não cabe no escopo, e o defeito não afeta o `make test`.

**Por que registrar mesmo assim:** a suíte completa esconder isso é sorte de distribuição
entre os três workers do `-n 3`. Quando ela mudar — mais um arquivo de teste, outro número de
workers no CI — vira falha intermitente sem causa aparente, que é o pior formato.

**Correção provável:** dar ao teste de caos um host próprio (ou zerar breaker e bucket num
fixture de `autouse`), de modo que ele não herde o estado de resiliência de ninguém.

**Segunda manifestação, na spec 115 — e ela confirma a hipótese.** O `make test` reprovou
em `test_public_api.py::test_limite_de_get_devolve_429_com_retry_after`: a requisição que
devia tomar 429 recebeu 200. O arquivo inteiro passa sozinho (16/16, 3,6 s) e a execução
seguinte da suíte completa fechou verde.

O mecanismo agora tem nome: o **token bucket de rate limit vive no Redis**, é global entre
workers por construção (spec 041, regra 4) e não participa do `ROLLBACK` por teste da 105.
Com `pytest -n 3`, outro worker gastando ou zerando a janela do mesmo host faz o teste de
limite ver uma janela que não é a dele. Era exatamente o candidato levantado na primeira
manifestação, e agora ele apareceu sozinho.

Isso amplia o alvo: não é «um teste de caos frágil», é **toda asserção sobre estado no
Redis** — rate limit, circuit breaker, cache — que hoje depende de nenhum vizinho ter
tocado a mesma chave.

**Correção provável, agora mais clara:** prefixar as chaves de Redis por worker do xdist
(`PYTEST_XDIST_WORKER`) no ambiente de teste, como a 105 fez com o banco. O isolamento por
transação resolveu o Postgres e deixou o Redis de fora.

**Spec-alvo:** 110 ou 120 — mesma auditoria da dívida 33, que já vai olhar isolamento e
gates. As três têm a mesma raiz: estado que sobrevive ao teste que o criou.
