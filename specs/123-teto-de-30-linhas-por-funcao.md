# 123 — Teto de 30 linhas por função (backend)

**Fase:** 12 · **Tipo:** refatoração · **Orçamento:** +0 s (o gate já existe)
**Depende de:** 122 · **Status:** ✅ concluída

---

## 1. Objetivo

Descer o teto de tamanho de função do backend de **40 para 30** linhas líquidas de corpo, e
trazer as 101 funções acima dele para dentro. **Terceiro e último degrau** da Nota de
execução da 121 — o número que a 121 pedia desde o começo.

> Refatoração: nenhuma mudança de comportamento. Nenhum contrato de API muda, nenhum teste
> anterior é editado.

## 2. Por que 30, e por que este é o último degrau

Trinta linhas é o que cabe numa tela sem rolar. Não é um número estético: é a distância em
que um revisor consegue segurar a função inteira na cabeça enquanto lê a última linha. Toda
a série 121→123 existe para chegar aqui; 50 e 40 foram degraus de execução, não alvos.

Medido em `c9776c4`, com o mesmo contador do gate:

| Teto | Funções acima | |
|---|---|---|
| 40 | 2 | as duas exceções versionadas da 122 |
| 38 | 16 | |
| 35 | 52 | |
| **30** | **103** | ← esta spec, sendo 2 já em exceção |

A 122 previu 103 e acertou. É o maior volume da série — mais que a 121 (20 funções) e a 122
(32) somadas —, mas cada função está no máximo 12 linhas acima do teto, e nenhuma passa de
42. Não existe um quarto degrau planejado: abaixo de 30 o gate começaria a brigar com
funções que já são um bloco só.

### A forma do que sobrou

Classificação por AST das 103, feita antes de escrever esta spec:

| Forma | Quantas | O corte que ela pede |
|---|---|---|
| misto (1–4 ramos) | 77 | extrair o ramo maior, ou a guarda inteira |
| sequência linear sem ramo | 19 | extrair o bloco do meio — normalmente a montagem da query |
| fluxo com 5+ ramos | 6 | tabela de despacho, como a 111 fez |
| mapeador puro | 1 | exceção (já é uma das duas da 122) |

A distribuição mudou de figura em relação à 122, onde o padrão dominante era sequência
linear longa. Aqui a maioria tem ramo — o que significa que **a lição da ordem das guardas
(§7) vale mais nesta spec do que valeu nas duas anteriores**.

### Onde elas estão

`domain/ai` (15), `domain/lawsuits` (13), `ai/tools` (9), `domain/bi` (6),
`domain/reports` (5). Os quatro primeiros são os contextos mais novos do projeto — o que é
consistente: a 106 e a 121 passaram pente fino no código antigo, e o de IA cresceu depois.

## 3. Escopo

**A.** `TETO_DE_LINHAS` de 40 para 30 em `tests/meta/test_tamanho_de_funcao.py`.

**B.** As 101 funções acima de 30 que não estão em `EXCECOES`, depois da recontagem
obrigatória da §9.

**C.** `docs/GATES.md` com o valor novo — o `test_registro_de_gates.py` reprova se divergir.

**D.** Revisar as 2 exceções herdadas da 122. Elas continuam válidas em 30 (mapeador de
campo puro não fica menor porque o teto desceu), mas a justificativa escrita precisa citar o
teto novo.

## 4. Fora de escopo

- Descer abaixo de 30. Não há quarto degrau, e abrir um exigiria medição nova.
- Frontend. Decidido ao fechar a 121: **não haverá** teto de tamanho de função lá, nem spec
  para isso. Ver dívida 38 — é escopo recusado, não pendência.
- Mudar a forma de contar. Mexer nela agora invalidaria a comparação entre os três degraus.
- Aumentar o teto de exceções. Continua **5 no projeto**, com 2 em uso.
- As dívidas 34 e 36. Se a refatoração passar de raspão por elas, registrar — não corrigir.

## 5. Modelo de dados / Contratos de API / Front-end

Nada. O contrato é o mesmo: 311 caminhos, 384 operações, 276 com parâmetros, e a prova é o
diff de `app.openapi()` antes e depois.

## 6. Regras de negócio

1. Nenhuma função de `app/` passa de 30 linhas líquidas de corpo.
2. Contagem líquida, como na 121: do primeiro statement executável ao último, com docstring,
   decoradores e assinatura de fora.
3. Toda função extraída é privada (`_nome`), **em inglês** (CLAUDE.md §9, decisão registrada
   na dívida 37), tipada, e `mypy --strict` continua verde sem exceção nova.
4. Docstring e comentário continuam em **português**.
5. Exceções versionadas: teto de **5 no projeto**, cada uma justificada. Com 2 herdadas,
   restam 3. Se precisar da sexta, o teto de 30 está errado para este código e a spec não
   fecha — essa conclusão vale mais que forçar o número.
6. Nenhum teste anterior é editado. Atualizar baseline numérico de meta-teste (como o
   `test_workers_finos`) é manutenção prevista, não edição de asserção.
7. Nenhum gate existente afrouxa para caber. Se uma extração estourar `max-args`,
   `max-branches` ou o orçamento de queries, o problema é a extração, não o gate.

## 7. O que as 121 e 122 aprenderam e esta spec herda

- **A ordem de guardas É comportamento.** Ao extrair `_template_if_running` na 121, a ordem
  de duas checagens foi invertida e mudou o que acontece quando o modelo some e o limite foi
  atingido. Os 30 testes do módulo passaram — o caso não é coberto. Com 77 das 103 funções
  desta spec tendo ramo, **esta é a lição de maior risco aqui**: ao extrair guarda, preservar
  a ordem e dizer no comentário por que ela é essa.
- **Compactar não é extrair.** Três tentativas de baixar uma função reescrevendo chamadas em
  menos linhas foram desfeitas pelo `black`, uma delas deixando a função MAIOR (59 → 62). O
  que funciona é tirar um bloco com nome.
- **Quando a função é fluxo, o corte é um objeto para o que viaja junto.** `_Call`,
  `_Attempt` e `_Spent` resolveram o que nenhuma extração de bloco resolvia — e sem eles o
  laço de retry bateria no `max-args` da 116.
- **Mapeador de campo não se parte.** A 122 provou por AST que duas funções eram um único
  `Return` com 40 e 24 campos `campo=obj.campo`. Não existe nome para "a primeira metade dos
  campos de um schema". Exceção, não extração — mas **só depois de classificar por AST**,
  nunca a olho.
- **Meta-teste morde sozinho.** Na 122, `test_workers_finos` exigiu a catraca atualizada e o
  teste de dívida com alvo no futuro pegou o número 122 reservado pela dívida 18. Rodar
  `pytest tests/meta` depois de cada lote, não só no fim.

## 8. Plano de testes

Nenhum teste novo. O gate é o `test_tamanho_de_funcao.py` que a 121 entregou, com o teto
baixado — e os três testes dele já foram provados mordendo na 122 (função nova acima do
teto, sexta exceção, exceção obsoleta).

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| — | os 1.616 testes existentes passam **sem edição** | — | 0 s |

**Total estimado:** +0 s.

## 9. Descobertas

### A recontagem, antes de qualquer edição

Medida em `c9776c4`, com o mesmo contador do gate:

| Acima de | Funções | Total do `app/` |
|---|---|---|
| 40 | 2 | 2.497 (as duas exceções da 122) |
| 38 | 16 | 2.497 |
| 35 | 52 | 2.497 |
| **30** | **103** | 2.497 |

A 122 projetou 103 e acertou. Descontadas as duas exceções herdadas, **101 funções** para
reestruturar — mais que a 121 (20) e a 122 (32) somadas.

### A forma prevista na §2 se confirmou, e mudou o método

A classificação por AST previu 77 com ramo, 19 lineares, 6 com cinco ou mais ramos e 1
mapeador. Bateu — e a consequência prática foi a que a §2 anunciou: **a lição da ordem de
guardas foi a que mais valeu**, porque a maioria tinha ramo.

Dois cortes exigiram inverter uma guarda para achatar o laço (`_retry_loop`, `run_sql`), e
nos dois casos os ramos eram mutuamente exclusivos — a inversão preserva a ordem observável.
Onde a ordem carregava significado, ela foi mantida com comentário: em `_log_failed_run`, o
`ROLLBACK TO` vem ANTES do log porque a sessão abortada recusaria o `INSERT` de auditoria, e
inverter trocaria o erro real do usuário por um erro do próprio código de auditoria.

### Nenhuma precisou de dois cortes — pelo mesmo motivo da 122

**Nenhuma das 101 exigiu mais de um corte.** As 103 estavam entre 31 e 42 linhas, no máximo
12 acima do teto, e todo bloco nomeável de uma função desse tamanho tem pelo menos 12 linhas.
O padrão se repetiu nos três degraus, e a razão é a forma da distribuição, não sorte.

Foram 70 arquivos e 120 auxiliares novos — mais que 101 porque algumas funções renderam dois
blocos nomeáveis (`_mark_failed`/`_mark_succeeded`, `_fields`/`_duplicate`,
`_money_fields`/`_closure_fields`), e extrair só um deixaria o segundo pela metade.

### A descoberta que evitou gastar exceções: quatro falsos mapeadores

A varredura por AST apontou **cinco** candidatos a mapeador puro. Com as duas exceções
herdadas isso daria **seis** — acima do teto de cinco da regra 5, e a spec teria que parar.

Lidos um a um, quatro **não** eram mapeadores:

| Função | O que tinha dentro |
|---|---|
| `extraction_router::_to_response` | uma compreensão de dicionário e um bloco condicional |
| `publications/router::_detail_to_response` | duas compreensões de lista |
| `lawsuits/router::_to_response` | 31 campos que formam **grupos com nome**: os valores financeiros, as datas do ciclo de vida |
| `listing::filters_from_query` | 30 campos, dos quais 10 são os **cinco intervalos de data** da listagem |

E aqui está a distinção que a 122 tinha formulado mas não precisara usar: *"a primeira metade
dos campos"* não tem nome, mas **"os valores financeiros do processo"** e **"as datas do
ciclo de vida"** têm. Um mapeador é impartível quando os campos não formam grupo nenhum — não
quando são muitos.

O teste automático é bom para **encontrar candidatos**, e ruim para **decidir**. As exceções
seguem em 2 de 5.

### O efeito colateral, de novo — e agora ele acabou

| Acima de | Antes da 123 | Depois |
|---|---|---|
| 30 | 103 | 0 (2 em exceção) |
| 25 | — | 108 |
| 20 | — | 267 |

A 121 herdou 118 acima de 30; a 122 entregou 103 para a 123 sem trabalhar nisso. Agora não há
degrau seguinte planejado: 108 acima de 25 seria um quarto ciclo brigando com funções que já
são um bloco só, e o ganho de legibilidade a partir daqui é discutível. **O teto para em 30**,
que é onde a 121 queria chegar.

### Duplicação caiu junto, sem ser o objetivo

O jscpd de Python saiu de **0,57% para 0,54%** — as cadeias de `except` repetidas viraram
tabelas de despacho. A de `documents/router.py` aparecia **três vezes idênticas** no mesmo
arquivo: é a regra dos 3 usos do §6 sendo cobrada por um gate de tamanho, e não pelo gate de
duplicação, que não a pegava (o bloco tem 6 linhas, abaixo do `min-lines` do jscpd).

### Dois meta-testes morderam, de novo

`test_workers_finos` cobrou a catraca duas vezes: `run_scheduled_sync` caiu de 26 para 15
statements e `refresh_aggregate` de 19 para 9. As duas entradas foram **removidas** do
baseline em vez de atualizadas, porque já cabem no teto de 15 — catraca para função que passa
é ruído que parece proteção, o mesmo princípio do `RUF100` da spec 113.

### Dois erros meus, os dois já catalogados

1. **Inserção por script entre `@dataclass` e a classe** — terceira ocorrência, depois da 106
   e da 122. Desta vez o conserto foi mecânico: um helper `insere_antes` que RECUA por linhas
   iniciadas em `@` ou `#` antes de inserir. Deixou de ser lição e virou código.
2. **Backtick não escapado em heredoc do shell** — o bash executou trechos da prosa de uma
   docstring e apagou seis identificadores dela. Achado porque o texto ficou sem sentido ao
   reler; a partir dali, todo script de edição passou a ser escrito em arquivo com heredoc
   **citado**, nunca interpolado.

E uma tentativa recusada, pela terceira vez na série: **compactar não é extrair**. Duas
funções foram "encolhidas" reescrevendo atribuições numa tupla — o `black` reexpandiu, o
`mypy` perdeu a inferência do tipo da lista, e o ganho foi zero. As duas viraram extração de
verdade.

## 10. Definição de pronto

- [x] Recontagem registrada em §9 **antes** de qualquer edição
- [x] `TETO_DE_LINHAS = 30`, gate verde
- [x] Nenhuma função de `app/` acima de 30 linhas líquidas
- [x] No máximo 5 exceções, versionadas e justificadas, com o teto novo citado
- [x] Auxiliares novos em inglês; docstrings em português
- [x] Nenhum teste anterior editado; contrato inalterado (311 caminhos, 384 operações)
- [x] `docs/GATES.md` com o valor novo
- [x] `make test` verde e wall-clock dentro do orçamento
- [x] `make lint` verde — repositório inteiro
- [x] `ROADMAP.md` com a linha da 123 em ✅
- [x] Commit `refactor(123): teto de 30 linhas por função no backend`
