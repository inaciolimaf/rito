# 139 — Três gates que não viam o que prometiam ver

**Fase:** 13 · **Tipo:** correção · **Orçamento:** +4 s de CPU (≈ +1,5 s de wall-clock)
**Depende de:** 009, 100, 118, 131, 132 · **Status:** ✅ concluída

---

## 1. Objetivo

Três gates do projeto passavam por motivos que não eram o mérito do código: o de camadas
só abria arquivos chamados `router.py` e `service.py`; o «teste do teste» do orçamento de
queries conferia o `len()` de uma lista em vez do instrumento; e os dois gates de jornada
de e2e só tinham teto, num runner que tratava «nenhuma jornada» como sucesso. Esta spec
amplia o que cada um enxerga, prova os três **mordendo nos dois lados** e escreve os
testes que a medição de mutação da spec 132 mostrou faltando em `app/core/listing.py` e
`app/domain/posts/recurrence_service.py`.

Correção: **nenhuma linha de `app/` é tocada.** Um bug custa um bug; um gate cego custa
todos os bugs que ele deixou passar e ainda ensina que a área está coberta.

## 2. Por que — o que foi medido

Base: auditoria de 08/09/2026 sobre o commit `dc0965d`, com caso plantado e controle para
cada achado.

| Gate | O que ele afirmava | O que ele media |
|---|---|---|
| Camadas (`test_camadas.py:93`) | as 3 regras do §5 em `app/domain/` | 39 + 39 arquivos; **16 invisíveis** |
| Orçamento de queries (`test_performance_invariants.py:130`) | «um contador que devolvesse sempre zero deixaria todo orçamento passar» | `len()` de uma lista que ele mesmo encheu |
| Jornadas e2e (`test_final_audit.py:150`, `journey-count.spec.ts:44`) | o teto de 25 do §3 | `0 <= 25` |

**Gate de camadas.** Um `vazamento_router.py` com `select()`, `session.execute()` e
`CustomerRepository` importado dava `4 passed`; o **mesmo arquivo** renomeado para
`router.py` dava `3 failed`. O que decidia entre verde e vermelho era o nome do arquivo.
E não era hipótese: havia duas violações vivas escondidas ali —
`documents/extraction_router.py:19,140` (`AttachmentRepository` dentro do router, a regra
2 literal) e `automations/engine.py:130` (`app.integrations.openrouter.factory` dentro do
motor, a frase literal do §5). Toda a camada de IA — o maior bloco novo do projeto — e
todo service de nome composto estavam fora.

**Orçamento de queries.** Neutralizando o listener (`create_engine('sqlite://')` no lugar
de `app.state.engine.sync_engine`), `test_performance_invariants.py` +
`test_query_budget.py` davam **`21 passed in 5.06s`**, com as 14 rotas medindo ZERO query.
O gate que o CLAUDE.md §11 chama de «gate, não aviso» desligava sem uma linha vermelha.

**Jornadas de e2e.** Apagar as nove jornadas deixava `make test` verde **e mais rápido** —
o wall-clock do §11 melhorava junto. Apagar o diretório inteiro nem subia o Playwright:
`run_e2e` imprimia «e2e: nenhuma jornada ainda — pulando» e saía com **exit 0**. O
`tests/meta/test_runner.sh` cobria três cenários e nenhum era esse `else` — a mesma
assinatura do achado da spec 131, um gate que via três de quatro casos.

**A lição é a da dívida 40**, e ela reaparece nos três: *verificação mecânica prova o que
ela mede, e o que ela mede precisa ser conferido contra o universo, não contra a própria
entrada*. A pergunta que faltava nunca foi «o gate passou?», foi «o gate LEU tudo o que
ele diz ler?».

## 3. Escopo

**A. O universo do gate de camadas passa a ser o PAPEL, não o nome.**

- **router** = `router.py`/`*_router.py` **ou** módulo que instancia `APIRouter`. As duas
  leituras coincidem hoje (46 arquivos, zero diferença) e as duas ficam: quem renomear o
  arquivo continua pego pelo `APIRouter`; quem trocar de framework continua pego pelo nome.
- **camada de regra** (escopo da regra 3) = todo módulo de `app/domain/` que não é router
  nem forma de dado (`models`, `schemas`, `repository`, `exceptions` e seus sufixados).
  110 arquivos, contra os 39 de antes.
- Os 17 arquivos que eram invisíveis viram **teste parametrizado nominal**
  (`test_o_gate_abre_os_routers_que_nao_se_chamam_router_py` e a irmã): um universo medido
  por `len()` encolhe de novo sem ninguém notar, porque o número continua parecendo grande.
- Contra-controle (`test_o_universo_nao_encolheu`): `models.py`, `schemas.py`,
  `repository.py` e `exceptions.py` continuam FORA. Sem ele, «ampliar o universo» e
  «desligar a classificação» seriam indistinguíveis.

**B. Os dois falsos positivos que a ampliação revelou, tratados na raiz.**

- `ai/threads_router.py:333` — `async for … in service.stream(…)` é um gerador do service,
  que é o que um router DEVE fazer. `stream` sai de `_METODOS_DE_EXECUCAO` e passa a
  denunciar só quando o receptor imediato é sessão/conexão. `execute` e `exec_driver_sql`
  continuam sem qualificação: nenhum service do projeto tem método com esses nomes.
- `templates/generate.py:11` — `DocumentMailer` **é um `Protocol`**, e mora em
  `messaging/document_email.py` ao lado do `SmtpDocumentMailer` concreto. A liberação é do
  **símbolo**, não do módulo (`_protocolos_de`): importar o `Protocol` passa, importar o
  mailer real do mesmo arquivo continua reprovando. Liberar o módulo inteiro teria
  liberado os dois.

**C. O piso do orçamento de queries.** `test_o_contador_conta_uma_requisicao_de_verdade`
faz uma requisição HTTP real dentro do mesmo `count_queries` que o gate usa e afirma
`log.count > 0`. Asserção de PISO, não de teto: o teto já é o gate, e teto sozinho não
distingue «o endpoint está enxuto» de «o instrumento parou de contar».

**D. O piso de jornadas de e2e, nos três pontos.** `PISO_DE_JORNADAS = 9` em
`test_final_audit.py`, `MIN_JOURNEYS = 9` em `journey-count.spec.ts`, e o `else` do
`run_e2e` virando `return 1`. Os três passam a contar a mesma coisa: `meta/` guarda gates
SOBRE as jornadas e não conta como jornada — inclusive no `find` do runner, que era por
onde o cenário «só o contador sobrou» ainda passava.

**E. Os testes que a mutação da spec 132 pediu.**

- `tests/unit/test_listing.py` (novo): a borda `23:59:59.999999` de `datetime_range`, os
  intervalos abertos, o `date_range` como controle e os quatro defaults de `Page`.
- `tests/integration/test_post_recurrence.py`: o delta dos campos relativos (regra 9 da
  spec 034) conferido pelo VALOR na 2ª e na 3ª ocorrência, e a ocorrência que cai
  exatamente sobre o `until_date`.

**F. Uma exceção nomeada, com data de validade.** `automations/engine.py` entra em
`EXCECOES_INTEGRACAO_EM_SERVICE` — ver §9. O `test_toda_excecao_ainda_viola_o_gate` faz a
linha se apagar sozinha no dia em que a injeção chegar.

## 4. Fora de escopo

- **Injetar o `AiRunner` nos oito pontos que constroem o `AutomationEngine`** — o conserto
  de verdade da violação do §9. É refatoração de nove arquivos, em quatro contextos que
  não são desta spec.
- **Os 246 testes cuja única asserção é um status code** e os 221 `except` cujo nome de
  exceção não aparece em `tests/` — medidos, registrados como dívida, grandes demais para
  aqui.
- **`QuickViews.__contains__`** (`app/core/listing.py:135-136`), código morto: proposto
  para remoção, não removido — o módulo é de outra frente neste ciclo. O `.names` da
  mesma classe, que a auditoria também dava como morto, **deixou de ser**: o
  `tests/unit/test_dia_do_escritorio_no_sql.py` (deste mesmo ciclo) o consome.
- **`docs/GATES.md`, `docs/DIVIDA-TECNICA.md` e `ROADMAP.md`** não foram editados
  (arquivos de outra frente neste ciclo). Os textos foram entregues para a integração.

## 5. Modelo de dados

Nenhuma migration. A spec não toca em schema.

## 6. Contratos de API

Inalterados. É o critério de aceite de uma correção de gate, e aqui ele é forte: **nenhum
arquivo de `app/` foi editado.**

## 7. Front-end

Nada.

## 8. Regras

1. O universo de um gate é o **papel** do arquivo, nunca o nome — e o papel é verificado
   contra a lista nominal do que ele precisa enxergar.
2. Ampliar um gate obriga a tratar os falsos positivos que a ampliação revela **na raiz**.
   Falso positivo mata gate tão rápido quanto falso negativo.
3. Todo gate que tem teto precisa de **piso**, quando zero satisfaz o teto.
4. Um «teste do teste» exercita o instrumento pelo caminho real, não um substituto dele.
5. `meta/` não é jornada — nos três lugares que contam jornada.
6. Exceção de gate é nominal, justificada por escrito e **reprova quando deixa de ser
   necessária**.
7. Todo gate corrigido é provado mordendo, com o caso plantado **e** o controle,
   versionados no próprio arquivo de teste.

## 9. A exceção — e por que ela não cabia nesta spec

`AutomationEngine.ai_runner` (`app/domain/automations/engine.py:130`) importa
`app.integrations.openrouter.factory` dentro de uma propriedade, para montar o provider
sob demanda. O comentário no código explica por quê: o motor é chamado de dentro de use
cases do domínio (`complete()`, `create()`, `change_stage()`), que não têm — e não devem
ter — acesso ao `app.state` onde o `lifespan` guarda o provider.

Tirar o import de lá é injetar o runner nos **oito** pontos que constroem o motor
(`lawsuits/service.py:153`, `lawsuits/board_service.py:199`, `posts/completion.py:33`,
`publications/service.py:159`, `automations/sweep.py:38,56`, `automations/router.py:212`)
e nas duas raízes de composição (`app/main.py` e o worker do Celery). Fazer pela metade
muda comportamento: sem o fallback, `DecisionRunner._blocker_to_ask` responde «Nenhuma IA
configurada neste servidor.» e **toda decisão por IA disparada por evento de domínio cai
no ramo padrão, em silêncio** — regressão de uma feature entregue (spec 094).

Por isso a exceção, e por isso ela é a primeira da história do gate. O que a impede de
virar gaveta são duas coisas: `test_as_listas_de_excecao_sao_exatamente_as_declaradas`,
que exige editar o teste para acrescentar outra; e `test_toda_excecao_ainda_viola_o_gate`,
que **reprova** no dia em que a entrada deixar de violar. A alternativa — deixar o gate
sem enxergar `engine.py` — é a doença que esta spec veio curar.

## 10. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| meta | router plantado com outro nome reprova as regras 1 e 2 | `tests/meta/test_camadas.py` | ~0,01 s |
| meta | router limpo **não** reprova (controle) | `tests/meta/test_camadas.py` | ~0,01 s |
| meta | `session.stream` reprova, `service.stream` não | `tests/meta/test_camadas.py` | ~0,01 s |
| meta | camada plantada com outro nome reprova a regra 3 | `tests/meta/test_camadas.py` | ~0,01 s |
| meta | contrato e `Protocol` **não** reprovam (controle) | `tests/meta/test_camadas.py` | ~0,01 s |
| meta | a implementação concreta do mesmo módulo reprova | `tests/meta/test_camadas.py` | ~0,01 s |
| meta | os 17 arquivos de camada sem o nome estão no universo | `tests/meta/test_camadas.py` | ~0,3 s |
| meta | `models.py`/`repository.py` continuam fora (contra-controle) | `tests/meta/test_camadas.py` | ~0,01 s |
| meta | exceção que não viola mais reprova | `tests/meta/test_camadas.py` | ~0,01 s |
| meta | o contador conta uma requisição de verdade (piso) | `tests/meta/test_performance_invariants.py` | ~0,3 s |
| meta | piso de jornadas reprova um e2e esvaziado (plantado + controle) | `tests/meta/test_final_audit.py` | ~0,01 s |
| meta | teto de jornadas reprova um e2e inchado | `tests/meta/test_final_audit.py` | ~0,01 s |
| runner | e2e sem jornada / diretório ausente derrubam o gate | `tests/meta/test_runner.sh` | ~0,1 s |
| runner | com jornada, `run_e2e` delega ao runner (controle) | `tests/meta/test_runner.sh` | ~0,1 s |
| e2e | piso e teto de jornadas, com caso plantado em `tmpdir` | `e2e/tests/meta/journey-count.spec.ts` | ~0,05 s |
| unit | borda `23:59:59.999999` de `datetime_range` + intervalos abertos | `tests/unit/test_listing.py` | ~0,03 s |
| unit | os quatro defaults de `Page` | `tests/unit/test_listing.py` | ~0,01 s |
| integração | o ciclo de prazos se preserva na 2ª e na 3ª ocorrência | `tests/integration/test_post_recurrence.py` | ~1,0 s |
| integração | a ocorrência que cai sobre o `until_date` é gerada | `tests/integration/test_post_recurrence.py` | ~0,5 s |

**Total medido:** +4 s de CPU no backend, ≈ +1,5 s de wall-clock (as três suítes rodam
concorrentes e o backend roda com `-n`). Onde ele foi: `test_camadas.py` de 0,24 s (4
testes) para 2,1 s (31 testes) — o universo passou de 78 arquivos para 156, e a
classificação é cacheada por isso; `test_post_recurrence.py` de 12 para 15 testes
(+1,6 s); o piso do contador de queries faz uma requisição HTTP (+0,4 s); o resto é ruído.
**Fixtures externas:** nenhuma. Nenhuma chamada de rede, nenhum LLM.

## 11. Descobertas

- **A ampliação achou exatamente dois falsos positivos, e os dois eram diagnosticáveis.**
  `service.stream(...)` e o `Protocol` no módulo errado. Nenhum dos dois pedia exceção:
  pediam uma leitura mais precisa, e é isso que a §3.B entrega. Um gate ampliado que
  ganhasse duas exceções teria trocado um problema por outro.
- **Uma das duas violações vivas foi consertada por outra frente no mesmo ciclo.**
  `documents/extraction_router.py` passou a usar `AttachmentService.get_accessible` —
  público desde a spec 135 justamente porque «a extração de documento buscava o anexo
  direto no repositório». O gate ampliado confirma o conserto e passa a defendê-lo.
- **O piso do contador nasceu vermelho no lugar certo.** Com o caso plantado, os 21 testes
  antigos continuam passando e só o novo falha — o que é a definição de o que faltava.
- **O mutante do delta encontra uma CHECK do banco antes da asserção.** `end_date - delta`
  produz término anterior ao compromisso e o `INSERT` estoura na constraint. O teste falha
  pelos dois motivos; o valor conferido é o que dá a mensagem legível.
- **`meta/` precisava sair da contagem em três lugares, não em um.** O
  `journey-count.spec.ts` já o excluía, o `test_final_audit.py` não (contava 10 onde o
  outro contava 9) e o `find` do `run_e2e` também não — e era por aí que o cenário «só o
  contador sobrou» continuava passando depois de o `else` virar falha.

## 12. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as regras com teste
- [x] Nenhuma tabela nova (nada de RLS a testar)
- [x] Os três gates provados **mordendo**, com os dois lados (reprova / não reprova),
      casos plantados versionados
- [x] Os três mutantes de `recurrence_service.py` e o de `listing.py` mortos, com a
      medição colada no relatório
- [x] `ruff`, `black` e `mypy --strict` verdes nos arquivos tocados
- [x] Sem `Any` e sem `# noqa`; um `# type: ignore[misc]` com justificativa na linha (é a
      atribuição que o `frozen=True` precisa recusar)
- [x] `docs/GATES.md`, `docs/DIVIDA-TECNICA.md` e `ROADMAP.md` — textos entregues para a
      integração (§4)
- [x] Commit `fix(139): três gates que não viam o que prometiam ver`
