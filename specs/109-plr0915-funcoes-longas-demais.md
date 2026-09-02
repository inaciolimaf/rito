# 109 — PLR0915: funções com corpo longo demais

**Fase:** 10 · **Tipo:** refatoração · **Orçamento:** +0 s (gate de lint)
**Depende de:** 106 · **Status:** ✅ concluída

---

## 1. Objetivo

Ligar `PLR0915` (too-many-statements) e quebrar as quatro funções que hoje passam do teto.
Complemento direto da 106: complexidade ciclomática mede caminhos, `PLR0915` mede volume — uma
função pode ter complexidade 3 e 200 linhas em sequência, e continuar sendo impossível de
revisar. As duas juntas cobrem as duas formas de uma função ficar grande.

> Refatoração: nenhuma mudança de comportamento.

## 2. Escopo

`pyproject.toml`, `[tool.ruff.lint]`: `select` ganha `PLR0915`. Teto default do Ruff: **50
statements**. Manter o default — é o número que a comunidade calibrou, e escolher outro sem
motivo medido é ruído.

Medido em 28/08/2026, commit `44469bd`, sobre `ruff check .`: **4 violações**.

| Arquivo:linha | Função | Statements |
|---|---|---|
| `app/main.py:149` | `create_app` | 70 |
| `app/domain/automations/engine.py:171` | `advance` | 61 |
| `app/domain/lawsuits/listing.py:216` | `_build_conditions` | 56 |
| `app/integrations/http/client.py:118` | `_request_com_resiliencia` | 54 |

## 3. Como corrigir cada uma

**`create_app` (70)** é o caso mais fácil e o menos interessante: é uma sequência linear de
`add_middleware`, `add_exception_handler` e `include_router`. Não tem regra dentro. Quebrar em
`_register_middlewares(app)`, `_register_error_handlers(app)` e `_register_routers(app)`
resolve e melhora a leitura de graça.

**As outras três já são alvo da 106** (`advance` cx 14, `_build_conditions` cx 23,
`_request_com_resiliencia` cx 15). Se a 106 fechar primeiro, é provável que este gate já
esteja verde para elas — **reconte antes de mexer**. Se ainda houver violação, o que sobrou é
volume sem ramificação, e a saída é extrair blocos nomeados, não achatar mais o fluxo.

## 4. Fora de escopo

- Tamanho de função **em linhas**. `PLR0915` conta statements, que é a métrica melhor: um
  `dict` literal de 40 linhas é 1 statement, e está certo que seja.
- ~~`max-lines-per-function` no ESLint. Spec futura.~~ **Não haverá.** Decidido ao fechar a 121: o frontend não terá teto de tamanho de função, nem spec para isso. Ver dívida 38.
- Reescrever a regra de negócio de `advance` ou do resolvedor de condições da listagem.

## 5. Modelo de dados / API / Front-end

Nada. `create_app` continua registrando exatamente os mesmos middlewares, handlers e routers,
na mesma ordem — **a ordem importa** (`CORSMiddleware` antes de `ObservabilityMiddleware`
antes de `PublicApiMiddleware`) e é o que o teste de aceite tem que provar.

## 6. Regras de negócio

1. `PLR0915` no `select`, teto default de 50 statements.
2. Nenhuma mudança de comportamento. Em particular, a ordem de registro de middleware em
   `create_app` é preservada.
3. Toda função extraída é privada (`_nome`), tipada, e vive no mesmo módulo.
4. Nenhum `# noqa: PLR0915`. Quatro ocorrências não justificam exceção.
5. Reconferir a contagem depois da 106 antes de começar: três dos quatro alvos são
   compartilhados, e trabalho já feito não se refaz.

## 7. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| meta | a ordem dos middlewares do app é a esperada, e nenhuma rota sumiu | `tests/meta/test_app_registry.py` | ~0,2 s |
| — | testes das specs 036, 052 e 092 passam sem edição | — | — |

**Total estimado:** +0,2 s

O meta-teste de ordem de middleware é o único teste novo que vale nesta spec: é exatamente a
propriedade que uma quebra de `create_app` pode destruir sem quebrar nenhum teste existente.

## 8. Descobertas

### Três das quatro já estavam resolvidas — a regra 5 valeu

A recontagem sobre `c55a17a` (fechamento da 106) deu **1 violação**, não 4. `advance`,
`_build_conditions` e `_request_com_resiliencia` caíram junto com a complexidade
ciclomática, exatamente como a §3 previu. Sobrou `create_app`, que a 106 nunca ia
alcançar: **complexidade ciclomática 1**, porque não tem um único `if`. É o caso que
justifica a spec existir — o `C901` não vê tamanho, e nenhum outro gate do projeto via.

### A decomposição que a spec propôs não passa no próprio gate

A §3 propõe `_register_middlewares` / `_register_error_handlers` / `_register_routers`. Os
dois primeiros ficam pequenos; o terceiro **não cabe**: são 61 chamadas a `include_router`,
ou seja, 61 statements contra o teto de 50. Quebrar em `_register_routers_a` e
`_register_routers_b` seria dividir por um critério que não existe.

A saída foi transformar as 61 chamadas em `_ROUTERS`, uma tupla de `(router, prefixo)` no
nível do módulo, percorrida por um laço de dois statements. É o mesmo movimento que a 106
fez dezenas de vezes — N blocos iguais pedindo uma tabela —, e aqui ele tem um ganho a
mais: **a ordem de registro vira dado legível de uma vez**, em vez de propriedade
emergente de uma sequência de 61 linhas.

Fica o registro para a spec que descer o `max-statements`: um teto numérico sobre uma
função que é uma **lista** empurra para tabela, não para funções menores. Isso é bom, mas
não é o que o nome da regra sugere.

### A ordem de registro é semântica, e agora está travada

O trabalho real desta spec não foi baixar 70 para 4. Foi identificar o que a quebra podia
destruir em silêncio e travar cada coisa:

1. **Ordem dos middlewares.** No Starlette o último adicionado é o mais externo, então a
   ordem de chamada é o inverso da ordem de execução — a leitura errada é fácil. O que
   importa é o CORS ser o mais **interno**: uma resposta produzida por middleware externo
   (um 429 do limite da API pública) que não passe pelo CORS chega ao navegador sem
   `Access-Control-Allow-Origin`, e o front mostra erro de origem em vez da mensagem real.
   A resposta certa existe e o usuário não a vê.
2. **Duas ordens de rota deliberadas.** `inbox` antes de `posts` e `publication_analysis`
   antes de `publications`. Trocar qualquer uma não levanta exceção: o handler errado
   responde 422 porque `"bulk"` não parseia como UUID. Nenhum teste de módulo vê isso,
   porque cada um chama a rota que lhe interessa.
3. **Router perdido.** Numa refatoração de 61 linhas, um `include_router` que não é
   transcrito não gera erro — as rotas simplesmente deixam de existir.
4. **Prefixo esquecido.** A tabela tem uma coluna de prefixo, e `""` é um valor válido: um
   router que devia estar em `/api/v1` e ficou em `""` publica a rota no lugar errado sem
   reclamar. É risco novo, introduzido pela própria tabela.

Os quatro viraram teste, e os quatro foram **provados mordendo**: introduzi cada defeito
de propósito e confirmei a reprovação antes de reverter. Um gate que ninguém viu falhar é
uma suposição.

### A ordem só se verifica pelo `openapi()`

`app.routes` não serve para verificar ordem de caminhos: no FastAPI 0.141 ele guarda 65
entradas, das quais 61 são wrappers internos (`_IncludedRouter`) que só se expandem na
resolução. Um teste que os inspecione quebra na próxima atualização da biblioteca.

O que serve é `app.openapi()["paths"]`: é `dict`, dict preserva ordem de inserção, e a
inserção segue a ordem de registro. API pública, estável, e devolve os 311 caminhos
achatados.

**Armadilha na verificação do contrato:** o dump de referência que eu usava foi gravado
com `sort_keys=True`, o que apaga justamente a ordem. Comparar contra ele diz que o
conteúdo é igual e **não diz nada sobre ordem**. A prova real veio de gerar a lista
ordenada num `git worktree` no HEAD limpo e comparar com a atual: idênticas, 311 a 311.

### Um erro de processo que o meta-teste da 100 pegou

Escrevi `specs/109-plr0915-funcoes-longas.md` do zero a partir da linha do `ROADMAP.md`,
sem conferir que `specs/109-plr0915-funcoes-longas-demais.md` já existia desde 29/08. O
`test_cabecalho_de_cada_spec_concorda_com_o_roadmap` reprovou com «mais de um arquivo para
o mesmo número» e o duplicado foi apagado.

Vale registrar porque o teste estava certo pelo motivo certo: duas specs com o mesmo
número são duas fontes de verdade, e a segunda teria contradito a primeira em detalhes
(nome do arquivo de teste, nomes das funções extraídas). O ciclo do `/loop` §8 diz «achar
a próxima spec não concluída» — não «escrever a próxima spec».

### Nomes de identificador: uma inconsistência que esta spec não resolve

O `CLAUDE.md` §9 manda identificadores em inglês. A 106 extraiu ~50 auxiliares e nomeou
**todas em português** (`_executar_passo`, `_aguardar_retentativa`, `_uso_somado`), e isso
está commitado. Esta spec nomeia em inglês porque a §3 dela nomeia as três funções
literalmente.

O resultado é `main.py` em inglês e `engine.py` em português, lado a lado. Não é o que
esta spec resolve — mas alguém tem que decidir, e o lugar é uma spec de refatoração
declarada. Fica anotado como achado, não corrigido.

## 9. Definição de pronto

- [x] `PLR0915` no `select`, teto default (50), com o gate provado reprovando 110 statements
- [x] `ruff check . --select PLR0915` limpo, sem `noqa` — nenhum foi preciso
- [x] Meta-teste de ordem de middleware e inventário de rotas, verde —
      `tests/meta/test_app_registry.py`, quatro casos, cada um provado mordendo
- [x] Nenhum teste anterior editado
- [x] Contrato inalterado: 311 caminhos, 384 operações, e a **ordem** dos 311 idêntica à
      do HEAD limpo (verificada em `git worktree`, não contra o dump ordenado)
- [x] `make test` verde e wall-clock dentro do orçamento
- [x] `make lint` verde — repositório inteiro
- [x] `ROADMAP.md` com a linha da 109 em ✅
- [x] Commit `refactor(109): funções longas demais`
