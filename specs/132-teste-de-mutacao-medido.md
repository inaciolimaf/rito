# 132 — Teste de mutação medido

**Fase:** 12 · **Tipo:** refatoração · **Orçamento:** +2 s no wall-clock
**Depende de:** 111, 117, 120, 124 · **Status:** ✅ concluída

---

## 1. Objetivo

Responder com **medição** à pergunta que a **dívida 7** deixou aberta desde a spec 010: a
suíte do Rito tem teste que passa por acidente? Três módulos de alto valor foram submetidos
a **182 mutações clássicas** por AST. Na primeira rodada, **84 mutantes sobreviveram** — 62
deles buracos de teste reais. Depois dos 27 testes que esta spec escreveu, sobram **24**, e
**nenhum** é buraco nos módulos medidos.

Refatoração: **nenhuma linha de `app/` muda.** Os testes anteriores passam sem edição.

## 2. Por que agora, e por que a dívida 7 estava desatualizada

A dívida 7 dizia, com todas as letras: *"Com **572 statements** e 99% de cobertura de linha,
o retorno de instalar uma ferramenta dedicada ainda é baixo"*, e marcava como gatilho
*"reavaliar na 020 ou quando a base de código crescer o suficiente para inspeção manual
deixar de ser confiável"*.

As duas condições venceram, e o número mudou de ordem de grandeza:

| Medida | Quando a dívida 7 foi escrita | Hoje (08/09/2026) |
|---|---:|---:|
| Statements em `app/` (sem `workers/`) | 572 | **24.663** |
| Arquivos em `app/` | — | **455** (431 sem `workers/`) |
| Testes coletados | — | **1.753**, em 207 arquivos |
| Piso de cobertura no CI | 99% (medido) | **83%** (`fail_under`, medido 83,79% na 124) |

**43 vezes maior.** A frase "verificado por inspeção manual" descreve um trabalho que
ninguém refez desde então e que ninguém consegue refazer: ler 24.663 statements procurando
asserção frouxa não é uma atividade, é uma esperança.

A segunda razão é o que o `docs/GATES.md` já admite em prosa: cobertura é **proxy**. "Uma
linha executada por um teste que não olha o resultado conta como coberta." Teste de mutação
é a única medição que ataca a propriedade em vez do proxy — e o resultado do §9 mostra que
os dois números divergem muito mais do que qualquer um esperava.

## 3. Escopo

**A. `backend/scripts/mutation.py`** — um mutador por AST, biblioteca padrão apenas, sem
dependência nova. Seis famílias de mutação (comparador, conectivo, aritmética, constante,
negação, chamada removida), controle de identidade obrigatório e reconferência do
sobrevivente contra uma suíte mais larga.

**B. A medição de três módulos**, com o relatório de sobreviventes classificado um a um (§9).

**C. Os testes que matam os sobreviventes reais** — 27 testes coletados em quatro arquivos:

| Arquivo | O que entra |
|---|---|
| `tests/unit/test_automation_conditions.py` (novo) | comportamento dos nove operadores de condição e do `validate_condition` |
| `tests/unit/test_sql_guard.py` | vocabulário financeiro como contrato, relação financeira, CTE que escreve, `LIMIT` ilegível, motivos de recusa |
| `tests/integration/test_rbac.py` | o degrau do MEIO da hierarquia de perfis |
| `tests/integration/test_financial_access.py` | a mensagem do 403 financeiro |

**D. A decisão sobre adotar ferramenta** — §7, regra 6.

## 4. Modelo de dados

Nenhuma migration. A spec não toca em schema.

## 5. Contratos de API

Inalterados. É o critério de aceite de uma refatoração, e aqui ele é forte: **nenhum arquivo
de `app/` foi editado.**

## 6. Front-end

Nada.

## 7. Regras

1. **A medição roda sobre uma CÓPIA da árvore**, nunca sobre o repositório. O mutador
   reescreve o arquivo alvo no lugar; apontá-lo para `backend/` deixaria a árvore corrompida
   se o processo morresse no meio.
2. **Controle de identidade obrigatório.** Antes do primeiro mutante, o módulo é reescrito
   por `ast.unparse` **sem** mutação e a suíte tem de passar. Sem isso, um mutante "morto"
   pode estar morto pela reescrita, não pela mutação, e o número inteiro é lixo.
3. **Sobrevivente é reconferido** contra uma suíte mais larga (`--confirm-tests`) antes de
   ser reportado. Sobrevivente é o produto desta spec; ele não pode ser artefato de ter
   rodado poucos testes.
4. **Todo sobrevivente é classificado** em uma de três categorias, e a classificação é
   humana: **buraco de teste** (a mutação muda comportamento e ninguém reclama),
   **equivalente** (a mutação não muda comportamento observável) ou **código morto**.
   Contagem de sobreviventes sem classificação não é resultado, é ansiedade.
5. **Mutação NUNCA entra no `make test`.** O CLAUDE.md §3 dá 300 s de wall-clock para as
   três suítes; um módulo de 80 statements custa 4 minutos. Fica como alvo próprio, sob
   demanda, no molde do `make test-nightly` — e **não** vira gate de CI (regra 6).
6. **Não se adota ferramenta de mutação como gate.** Justificativa medida no §9: o escore de
   mutação depende de classificar equivalentes à mão, e um gate que precisa de um humano
   para dizer se o vermelho vale não é gate — é revisão com etapa a mais. O que fica é a
   ferramenta sob demanda, e a regra de quando usá-la (regra 7).
7. **Quem escreve spec nova de guardrail, de autorização ou de função pura de decisão roda o
   mutador uma vez no módulo que tocou.** São as três famílias onde o §9 achou 100% dos
   buracos graves. Recomendação em prosa, não gate — pelo motivo da regra 6.
8. **Fora de escopo, e vinculante:** `app/core/dates.py` (avaliado, §9), `app/workers/`
   (fora até da medição de cobertura, spec 117 regra 4) e qualquer correção em `app/`. Os
   dois defeitos de produto que a medição encontrou viram dívida, não commit desta spec.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| unit | `eq` compara por texto (UUID × string), não por identidade | `tests/unit/test_automation_conditions.py` | ~0,01 s |
| unit | `eq` com `None` de um lado, dos dois, e contra `false` | idem | ~0,01 s |
| unit | `eq` com booleano de um lado compara como booleano | idem | ~0,01 s |
| unit | `ne` é a negação de `eq` | idem | ~0,01 s |
| unit | `exists` olha presença, não verdade (`0` existe) | idem | ~0,01 s |
| unit | `empty` cobre `None`, `""` e `[]` | idem | ~0,01 s |
| unit | `in` exige lista do lado esperado | idem | ~0,01 s |
| unit | os quatro operadores de ordem na borda de valores iguais | idem | ~0,01 s |
| unit | ordem com `None` de qualquer lado não satisfaz | idem | ~0,01 s |
| unit | condição sem `op` usa `eq` | idem | ~0,01 s |
| unit | operador desconhecido registra aviso (`caplog`) | idem | ~0,01 s |
| unit | `validate_condition`: aceita ausência e operador padrão | idem | ~0,01 s |
| unit | `validate_condition`: exige campo, com a mensagem inteira | idem | ~0,01 s |
| unit | `validate_condition`: recusa operador fora do contrato, com a mensagem inteira | idem | ~0,01 s |
| unit | vocabulário financeiro escrito duas vezes (2 listas + `MAX_ROWS`) | `tests/unit/test_sql_guard.py` | ~0,01 s |
| unit | relação financeira exige acesso mesmo sem coluna de dinheiro (×2) | idem | ~0,02 s |
| unit | CTE que escreve é barrada mesmo com `SELECT` na raiz | idem | ~0,01 s |
| unit | `LIMIT` que não dá para ler cai no teto | idem | ~0,01 s |
| unit | todo motivo de recusa chega inteiro ao usuário (×3) | idem | ~0,02 s |
| unit | SQL ilegível diz o que o parser reclamou | idem | ~0,01 s |
| unit | a recusa por allowlist nomeia TODAS as relações barradas | idem | ~0,01 s |
| integração | Administrador toma 403 em rota de Gestor (mensagem inteira) | `tests/integration/test_rbac.py` | ~0,4 s |
| integração | Colaborador toma 403 em rota de Administrador (mensagem inteira) | idem | ~0,4 s |
| integração | o 403 do financeiro diz qual acesso falta | `tests/integration/test_financial_access.py` | ~0,4 s |

**Total estimado:** +2 s (medido: ~1,5 s em série; menos sob `pytest -n auto`)
**Fixtures externas:** nenhuma. Nada aqui toca a rede.

Os 1.726 testes anteriores passam **sem edição** — é o que prova que nenhum comportamento
mudou. Os 123 meta-testes (`tests/meta/`) continuam verdes.

## 9. Descobertas

### 9.1 A ferramenta: `mutmut` avaliado, mutador próprio escolhido

Há rede nesta máquina e o `mutmut` **3.7.0** instala sem problema (`uv run --with mutmut`).
Ele foi recusado por dois motivos concretos, nenhum deles "não deu para instalar":

1. **Exige configuração num arquivo que não existe.** `mutmut` 3.x falha com
   `Could not figure out where the code to mutate is. Please specify it by adding
   "source_paths=code_dir" in setup.cfg to the [mutmut] section.` Um `setup.cfg` novo na raiz
   do backend, permanente, para um experimento de três arquivos.
2. **Materializa uma cópia da árvore em `mutants/`** e instrumenta cada função com um
   *trampolim* — um diretório de código gerado dentro do repositório, com o
   `on_dependency_change` a gerenciar. Para 24.663 statements, é uma segunda árvore.

O `scripts/mutation.py` tem ~300 linhas, **zero dependência nova** (biblioteca padrão +
`pytest`, que já está lá) e cabe numa leitura. Ele usa `os.fork` + `pytest.main` em vez de
`subprocess`: economiza ~0,9 s dos 1,4 s de cada mutante e evita um `# noqa: S603` que não
teria onde caber — o teto de silenciamento de `S*` do projeto está em 6 de 6
(`docs/GATES.md` §1).

O `cosmic-ray` não foi testado: ele resolve o mesmo problema com mais infraestrutura
(banco de sessão próprio, distribuição por Celery), e a decisão da regra 6 tornaria a
avaliação acadêmica.

### 9.2 Os três módulos, e por que estes

`app/core/permissions.py` (29 statements), `app/domain/automations/conditions.py` (50) e
`app/domain/ai/sql_guard.py` (80). **159 statements, 0,6% de `app/`** — de propósito: o
valor de um sobrevivente não é uniforme pelo código.

- **`permissions.py`** decide autorização. Mutante vivo ali é escalada de privilégio.
- **`conditions.py`** já provou, na **dívida 36**, que decide errado em silêncio: até a spec
  124, operador não reconhecido se comportava como `lte` dentro de uma automação.
- **`sql_guard.py`** é guardrail. A spec 089 é explícita: "guardrail que depende de outro
  para funcionar não é guardrail". Mutante vivo ali é uma camada que não está lá.

**`app/core/dates.py` foi avaliado e ficou de fora** (regra 8). Ele gera 139 mutantes — mais
que os três juntos — e é aritmética pura: um sobrevivente ali erra uma data, que é ruim, mas
é a mesma classe de defeito que os testes de borda já cobrem por construção. Os três
escolhidos erram *autorização*, *decisão* e *contenção*, e nenhum deles tem borda óbvia para
um autor de teste enxergar. Fica registrado como candidato natural da próxima rodada.

### 9.3 O número: 84 sobreviventes de 182, e o que cobertura não via

| Módulo | Mutantes | Rodada 1: mortos | Rodada 1: vivos | Escore |
|---|---:|---:|---:|---:|
| `app/core/permissions.py` | 49 | 28 | 21 | 57,1% |
| `app/domain/automations/conditions.py` | 68 | 35 | 33 | 51,5% |
| `app/domain/ai/sql_guard.py` | 65 | 35 | 30 | 53,8% |
| **Total** | **182** | **98** | **84** | **53,8%** |

Os três módulos estão **integralmente cobertos por linha**. O escore de mutação é 53,8%.
Essa distância — 100% de proxy contra 53,8% de propriedade — é a resposta que a dívida 7
pedia, e ela é o contrário do que a dívida supunha.

**Classificação dos 84** (regra 4): **62 buracos de teste**, **19 equivalentes**, **3 código
morto**.

### 9.4 Os sobreviventes, um a um

#### `app/core/permissions.py` — 21 vivos

| Linha | Mutação | Classe | O que significa |
|---|---|---|---|
| 20 | `COLABORADOR: 0 → 1` | **buraco** | empata Colaborador com Administrador: um Colaborador entra em rota de Administrador |
| 21 | `ADMINISTRADOR: 1 → 0` | **buraco** | idem, pelo outro lado |
| 21 | `ADMINISTRADOR: 1 → 2` | **buraco** | empata Administrador com Gestor: um Administrador entra em rota de Gestor |
| 22 | `GESTOR: 2 → 1` | **buraco** | idem, pelo outro lado |
| 71 | `'Exige perfil ' → ''` | **buraco** | a frase do 403 nunca foi conferida inteira |
| 71 | `' ou superior.' → ''` | **buraco** | idem |
| 83 | `'Exige acesso financeiro ' → ''` | **buraco** | idem, no 403 financeiro |
| 83 | `' ou superior.' → ''` | **buraco** | idem |
| 44 | `'goals.manage' → ''` | **código morto** | capacidade declarada e consumida em **lugar nenhum** — nem no backend, nem no front |
| 45 | `'taxonomies.manage' → ''` | **código morto** | idem |
| 9–14 (6) | entradas de `__all__` → `''` | equivalente | `__all__` só governa `import *`, que ninguém usa |
| 20, 28 | `0 → -1` | equivalente | a ordem RELATIVA é o que decide; deslocar a escala não muda nada |
| 22, 30 | `2 → 3` | equivalente | idem |
| 64 | `'_rito_permission_dependency' → ''` | equivalente | a constante é usada simetricamente no `setattr` e no `getattr` |

**O achado.** `test_rbac.py` tinha exatamente dois testes, e os dois nos **extremos**:
Colaborador barrado no topo, Gestor passando no meio. Nada no repositório inteiro
distinguia ADMINISTRADOR de GESTOR nem de COLABORADOR. Trocar um ordinal de `_ROLE_ORDER`
empatava dois perfis e a suíte inteira — 1.726 testes, `test_permission_coverage.py`,
`test_financial_permission_sweep.py`, `test_dispatch_tables.py` — ficava verde.

Vale notar o que **cada gate existente provava, e não provava**: o
`test_dispatch_tables.py` da spec 111 garante que `_ROLE_ORDER` tem os três papéis; o
`test_permission_coverage.py` garante que toda rota declara uma permissão. Presença e
declaração. **A ordem entre os três valores não era propriedade de ninguém.**

A contraprova de que os quatro são buracos e não equivalentes: `0 → -1` e `2 → 3` — que
preservam a ordem — sobreviveram e continuam sobrevivendo, corretamente classificados como
equivalentes. A distinção não é opinião; ela é exatamente onde os dois testes novos mordem.

#### `app/domain/automations/conditions.py` — 33 vivos

**32 buracos, 1 equivalente**, e todos com uma causa só.

| Linhas | Mutações | O que significa |
|---|---|---|
| 22–31 (8) | `or → and`, `'op' → ''`, `'eq' → ''` e as 4 partes das duas mensagens | `validate_condition` — o 422 de quem monta a automação — **não tinha teste nenhum** |
| 39 | `'eq' → ''` | condição sem `op` explícito deixaria de comparar por igualdade e passaria a nunca satisfazer |
| 60–67 (6) | `or → and` (×2), `is → is not` (×3), `== → !=` | **`_same` inteira**: a comparação por texto que existe para um `UUID` do banco casar com uma string do JSON. O `== → !=` inverte o operador `eq` do produto e nada reclamava |
| 73, 74, 76 | `> → >=`, `< → <=`, `<= → <` | três dos quatro operadores de ordem **sem caso de borda**: o único teste usava `1` e `2`, e valores diferentes não separam `gt` de `gte` |
| 85, 86 (4) | `or → and`, `is → is not` (×2), `False → True` | comparação de ordem com `None` de um lado: o mutante faz `"None" > "AAA"` decidir a automação, e o `False → True` faz a ação **disparar** |
| 99 | remove `logger.warning(...)` | o aviso que a correção da dívida 36 introduziu — sem ele, a automação que não roda volta a não ter causa visível |
| 108–112 (10) | `is not → is`, `or → and`, `== → !=` (×2), `in → not in`, `False → True`, `not X → X`, `'' → texto` | **os cinco operadores de `_OPERATORS_BY_NAME` (`eq`, `ne`, `in`, `exists`, `empty`) nunca eram executados** |
| 38 | `'' → texto` (default de `field`) | equivalente: os dois valores caem em `_lookup` e devolvem `None` |

**O achado, e ele é sobre os gates da casa.** Dos nove operadores que `OPERATORS` declara, só
os **quatro de ordem** eram executados por algum teste — e três deles sem borda. Os cinco de
igualdade e presença tinham dois gates apontados para eles, e nenhum dos dois olhava
comportamento:

- `test_automations_dispatch.py` (spec 111) prova que **a chave existe na tabela**. A lambda
  por trás da chave pode fazer o oposto do que promete;
- a cobertura de linha marca as cinco lambdas como **cobertas**, porque o `dict` literal
  executa no `import` do módulo.

É a demonstração mais limpa que esta spec produziu de por que cobertura é proxy: 100% de
linha, dois meta-testes dedicados, e nenhuma das cinco decisões verificada.

#### `app/domain/ai/sql_guard.py` — 30 vivos

| Linhas | Mutação | Classe | O que significa |
|---|---|---|---|
| 52, 53 | as duas entradas de `FINANCIAL_RELATIONS` → `''` | **buraco (grave)** | o recorte financeiro tem duas portas — a coluna e a **relação** — e só a da coluna tinha teste. Apagar `bi_cost_allocation_visible` da lista liberava a view inteira para quem não tem acesso financeiro |
| 57 (6) | `closed_fees`, `avg_fees`, `cost`, `amount`, `balance`, `revenue` → `''` | **buraco (grave)** | só `total_case_value` era exercitado; os outros seis nomes eram vocabulário sem guarda |
| 196 | `MAX_ROWS + 1 → MAX_ROWS - 1` e `+ 1 → + 0` | **buraco** | o ramo do `LIMIT` ilegível devolvia a consulta **sem teto** e nada reclamava |
| 28 | `MAX_ROWS: 1000 → 1001 / 999` | **buraco** | o teto é conferido em toda parte contra a própria constante (`endswith(f"LIMIT {MAX_ROWS}")`) — asserção que não pode falhar, exatamente o "teste que passa por acidente" da dívida 7 |
| 30 | `STATEMENT_TIMEOUT_MS: 5000 → ±1` | **buraco (fora do módulo)** | a constante é consumida em `app/domain/ai/analytics.py:414`; o valor não é conferido em teste nenhum. Fica registrado, não fechado aqui (regra 8) |
| 103, 107, 128, 142, 150, 155, 156 | as mensagens de recusa → `''` | **buraco** | a regra 2 da spec 089 diz que o motivo vai para a tela do usuário; os testes olhavam o tipo da exceção ou um pedaço da frase |
| 65 | remove `super().__init__(reason)` | equivalente | `BaseException.__new__` já grava `args`; `str(exc)` devolve o motivo do mesmo jeito. **A linha é redundante** — descoberta só porque o mutante insistiu em sobreviver aos testes novos |
| 111 | `return arvores[0] → arvores[-1]` | equivalente | o `if len(arvores) != 1` logo acima garante que os dois são o mesmo elemento |
| 197 | `valor > MAX_ROWS → >=` | equivalente | na borda os dois caminhos emitem `LIMIT 1000` |
| 196 | `MAX_ROWS + 1 → MAX_ROWS + 2` | equivalente | é uma sentinela; qualquer valor acima do teto serve |
| 101 | `rstrip(';') → rstrip('')` | equivalente | a docstring justifica o `rstrip` com "o ponto e vírgula final não virar um segundo comando vazio"; nesta versão do `sqlglot` o `parse` já descarta o comando vazio. A linha é cinto sobre suspensório |
| 101 | `(raw_sql or '') → (raw_sql or texto)` | equivalente | muda só a mensagem de um caminho já rejeitado |
| 26 | `DIALECT: 'postgres' → ''` | equivalente | conferido: o dialeto genérico do `sqlglot` analisa e reemite as consultas do catálogo igual. Não vale em geral, vale para este vocabulário |
| 69 | `@dataclass(frozen=True) → False` | equivalente | ninguém muta um `CheckedSql` |
| 189 | mensagem sob `# pragma: no cover` → `''` | **código morto** | declarado inalcançável pelo próprio código |

### 9.5 Depois dos testes: 158 de 182

| Módulo | Mutantes | Mortos | Vivos | Escore |
|---|---:|---:|---:|---:|
| `app/core/permissions.py` | 49 | 36 | 13 | 73,5% |
| `app/domain/automations/conditions.py` | 68 | 67 | 1 | **98,5%** |
| `app/domain/ai/sql_guard.py` | 65 | 55 | 10 | 84,6% |
| **Total** | **182** | **158** | **24** | **86,8%** |

Os 24 restantes: **19 equivalentes**, **3 código morto**, **2 buracos fora do módulo** (a
constante `STATEMENT_TIMEOUT_MS`, consumida no `analytics.py`). **Nenhum buraco de teste
aberto nos três módulos medidos.**

Vale dizer o que o escore de 73,5% do `permissions.py` significa depois disso: ele é o teto
daquele arquivo. Onze dos treze sobreviventes são equivalentes por construção — deslocar
toda a escala de `_ROLE_ORDER` não pode ser detectado por teste nenhum, porque não muda
comportamento. **Escore de mutação não é uma nota que se persegue até 100%**, e é por isso
que ele não vira gate (regra 6).

### 9.6 Dois defeitos de produto, encontrados e NÃO corrigidos aqui

A regra 8 é vinculante: esta spec não edita `app/`. Os dois viram dívida.

1. **`_with_limit` deixa passar `LIMIT` com aritmética.** `limite.expression.name` sobre um
   nó `Add` devolve o literal da **esquerda**, então `int(...)` funciona e o teto não é
   aplicado. Medido:

   ```
   SELECT month FROM ai_allowed_metrics LIMIT 0+5000000
     →  SELECT month FROM ai_allowed_metrics LIMIT 0 + 5000000
   ```

   A regra 5 da spec 089 diz "teto de linhas **sempre** presente"; aqui ele não está.
   Gravidade moderada: quem escreve a consulta é o modelo, não o usuário — mas a proteção
   contra um `LIMIT` "gerado sem malícia", que é a justificativa escrita na própria
   docstring, não vale para esta forma. O teste que esta spec escreveu cobre o `LIMIT`
   ilegível (`LIMIT (SELECT 5)`) e o ausente (`LIMIT ALL`), **não** este.

2. **`_same` coage string a booleano.** Quando um dos lados é `bool`, a comparação vira
   `bool(atual) is bool(esperado)` — e `bool("false")` é `True`. Uma condição
   `{campo: flag, op: eq, value: "false"}` casa com `flag = True`. Se o valor da condição
   sempre chegar como booleano de JSON, o caminho não acontece; se a tela de automação
   guardar o valor como texto, acontece. É a mesma família da dívida 36 (decidir errado em
   silêncio), e precisa de quem conheça o formulário da 092 para dizer se é alcançável.

### 9.7 Por que não vira gate — a conta

Extrapolação do medido: 182 mutantes para 159 statements, ou **1,15 mutante por statement**.
Para os 24.663 statements de `app/` (sem `workers/`), são **~28.400 mutantes**. A **1,4 s**
por mutante — que é a suíte mais barata que existe neste projeto, três arquivos de teste
unitário — dá **11 horas**. Com a suíte de backend inteira (43 s), **duas semanas**.

O CLAUDE.md §3 dá **300 s** para as três suítes juntas. Não há aritmética que aproxime as
duas coisas, e é a mesma razão pela qual o perfilamento com volume real da spec 098 mora no
`make test-nightly`: medição cara não deixa de valer, ela deixa de caber no PR.

E há um motivo que não é de tempo: **22 dos 84 sobreviventes (26%) eram equivalentes ou
código morto**, e distingui-los exigiu ler o código. Um gate que produz vermelho a ser
triado por um humano treina o time a ignorá-lo — é a lição que a spec 110 já tinha aprendido
sobre gate com lista de exceção. Fica a ferramenta e a regra 7, que é onde o retorno estava.

### 9.8 O que esta spec NÃO cobre

- **Só três módulos, 0,6% de `app/`.** A afirmação desta spec é sobre eles, não sobre a
  suíte inteira. Um escore de 53,8% em três módulos escolhidos por serem críticos **não**
  autoriza dizer "a suíte do Rito mata metade dos defeitos" — módulo crítico é onde o teste
  costuma ser mais denso, não menos, o que torna o número um limite superior otimista tanto
  quanto pessimista. Ninguém sabe, e esta spec não descobre.
- **Seis famílias de mutação, não todas.** Não há troca de argumento em chamada, remoção de
  `return`, nem mutação de decorador ou de `except`. Um mutador maior acharia mais.
- **Nada no frontend.** Vitest tem `stryker`; o piso de cobertura de lá é 53%, e o que uma
  medição de mutação encontraria naquele número é previsível o bastante para não valer o
  ciclo.
- **Não há gate que impeça o buraco de voltar.** Se alguém apagar
  `test_administrador_gets_403_on_gestor_route`, o `permissions.py` volta a 57%, e só a
  próxima rodada manual descobre. Isso é uma consequência aceita da regra 6, não um descuido.

### 9.9 Nota de método: o número 132 era reservado

O `docs/DIVIDA-TECNICA.md` re-atribuiu a **dívida 7** para a spec 132 na 131, e o gate
`test_nenhuma_spec_ocupa_numero_que_uma_divida_aberta_reserva` cobra que a spec **cite** a
dívida que consome. Esta cita, e resolve. É a primeira vez na série em que a nota de método
da 124 funcionou como pretendido — o número foi escolhido pela dívida, não pela fila.

## 10. Definição de pronto

- [x] Escopo implementado, nada além — **nenhum arquivo de `app/` editado**
- [x] Todas as regras com teste, ou com a medição que as sustenta (§9)
- [x] Nenhuma tabela nova (nada de RLS a testar)
- [x] Os 1.726 testes anteriores passam sem edição; os 123 meta-testes verdes
- [x] `make lint` verde nos arquivos tocados (`ruff`, `black`, `mypy --strict`)
- [x] Sem `Any`, `# type: ignore` ou `# noqa` sem justificativa — e **nenhum `# noqa` novo**
- [x] Sem dependência nova no `pyproject.toml`
- [x] Mutação **fora** do `make test` (CLAUDE.md §3)
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `refactor(132): teste de mutação medido`
