# 111 — PLR0912: ramos demais

**Fase:** 11 · **Tipo:** refatoração · **Orçamento:** +0 s (gate de lint)
**Depende de:** 106, 109 · **Status:** ✅ concluída

---

## 1. Objetivo

Ligar `PLR0912` (too-many-branches) e resolver as seis funções acima do teto. É o terceiro
lado do mesmo triângulo: a 106 mede caminhos, a 109 mede volume, esta mede **ramificação** —
quantos `if`/`elif`/`for`/`except` uma função empilha. Uma função pode passar nas duas
anteriores e ainda ser uma árvore de decisão que ninguém consegue cobrir de teste.

> Refatoração: nenhuma mudança de comportamento.

## 2. Escopo

`pyproject.toml`: `select` ganha `PLR0912`. Teto default do Ruff: **12 ramos**. Manter.

Medido em 28/08/2026, commit `44469bd`, sobre `ruff check .`: **6 violações**.

| Arquivo:linha | Função | Ramos |
|---|---|---|
| `app/domain/lawsuits/listing.py:216` | `_build_conditions` | 22 |
| `app/domain/templates/variables.py:138` | `_resolve_lawsuit` | 19 |
| `app/domain/templates/variables.py:95` | `_resolve_customer` | 17 |
| `app/integrations/http/client.py:118` | `_request_com_resiliencia` | 14 |
| `app/domain/automations/engine.py:171` | `advance` | 13 |
| `app/domain/lawsuits/cnj.py:120` | `infer_court_code` | 13 |

**Sobreposição total com a 106.** As seis estão na lista das 41. Se a 106 fechar antes, a
primeira tarefa desta spec é recontar — pode não sobrar nada além de ligar a regra, e isso é
um bom resultado, não um problema.

## 3. O padrão por trás de cinco das seis

Cinco destas funções são a mesma forma: **despacho por valor**, escrito como cadeia de
`if/elif`.

- `_resolve_customer` e `_resolve_lawsuit` despacham por nome de variável de modelo;
- `infer_court_code` despacha por segmento do CNJ;
- `_build_conditions` despacha por campo de filtro;
- `advance` despacha por tipo de passo da automação.

A correção estrutural, em todos, é um mapa `dict[Chave, Callable]` no nível do módulo. Além de
zerar a ramificação, ela transforma «apareceu um valor novo do enum e ninguém tratou» de um
`else` silencioso num erro de `mypy --strict` — que é o ganho real, maior que o número do lint.

`_request_com_resiliencia` é a exceção: a ramificação ali é de **política de retry** (status,
timeout, tentativa, backoff), não despacho. A saída é extrair as decisões em predicados
nomeados (`_deve_repetir`, `_espera_ate`), não uma tabela.

## 4. Fora de escopo

- `PLR0911` (returns demais) — spec 112. Há sobreposição em `infer_court_code` e nas duas
  `_resolve_*`; quem chegar primeiro colhe.
- Mudar o algoritmo de retry do cliente HTTP. Só a forma muda.
- A taxonomia de segmentos do CNJ.

## 5. Modelo de dados / API / Front-end

Nada.

## 6. Regras de negócio

1. `PLR0912` no `select`, teto default de 12.
2. Nenhuma mudança de comportamento: os testes das specs de origem passam sem edição.
3. Onde a correção for tabela de despacho, ela é **exaustiva sobre o enum** e o `mypy` prova
   isso — nada de `.get(chave, default_silencioso)` escondendo um caso não tratado.
4. Nenhum `# noqa: PLR0912`.
5. Recontar depois da 106 antes de começar.

## 7. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| unit | toda chave do enum de passo de automação tem entrada na tabela de despacho | `tests/unit/test_automations_dispatch.py` | ~0,1 s |
| unit | todo nome de variável de modelo declarado tem resolvedor | `tests/unit/test_template_variables.py` (estende) | ~0,1 s |
| — | testes das specs 026, 066, 092 e 088 passam sem edição | — | — |

**Total estimado:** +0,2 s

Os dois testes novos existem porque a tabela de despacho cria uma classe de bug que o
`if/elif` não tinha: uma chave esquecida. Ligar a regra sem eles troca um problema por outro.

## 8. Descobertas

### As seis já estavam resolvidas — e o teto de 12 teria sido decoração

Recontagem sobre `ab4827b` (fechamento da 109): **zero violações a 12**. Zero também a 10,
e zero a 8. A §2 previu isso («pode não sobrar nada além de ligar a regra, e isso é um bom
resultado»), e o previsto aconteceu: as seis funções da tabela caíram junto com a
complexidade ciclomática na 106.

Mas ligar a regra em 12 entregaria um gate que **não pode disparar**. A função mais
ramificada do projeto tem 8 ramos e nenhuma chega a 9; um teto em 12 nunca reprovaria nada
enquanto o `max-complexity = 6` estivesse em vigor. Isso contraria o §11 do `CLAUDE.md`,
que trata gate como reprovação e não como aviso.

**Desvio declarado da §2 desta spec:** o teto entrou em **8**, não nos 12 do padrão. Custa
zero hoje (nenhuma violação) e passa a valer como catraca: nenhuma função pode ficar mais
ramificada que a mais ramificada de hoje. Se a intenção original era mesmo 12, é uma linha
no `pyproject.toml`.

### `PLR0912` não é redundante com o `C901` — e a diferença tem nome

A suspeita natural é que as duas regras meçam a mesma coisa. Não medem, e a prova está no
próprio projeto: `app/workers/djen_sync.py::run_due_syncs` tem **complexidade ciclomática 6**
(exatamente no teto da 106) e **8 ramos**.

A diferença é o `else`. Para o mccabe, um `if/else` é **uma** decisão; para o `PLR0912`, são
**dois** ramos. Uma função que decide pouco mas se abre em muitos caminhos — o padrão de
quem monta contexto de execução com vários fallbacks — passa no `C901` e é justamente o que
o `PLR0912` pega.

Isso responde a pergunta que a §9 da 106 deixou em aberto («o que a spec de PLR0912 vai
encontrar já resolvido»): encontrou tudo resolvido em número, mas a regra continua valendo
por medir uma dimensão que a outra não vê.

### O trabalho real foi a exaustividade, não a ramificação

Sem violações a corrigir, o que sobrou é o que a §7 já apontava como o ponto: a 106 trocou
dezenas de cadeias de `if/elif` por tabelas de despacho, e **a troca muda o modo de
falhar**. O `if/elif` erra alto — cai no `else` e alguém percebe. A tabela erra baixo: uma
chave esquecida devolve `None` no `.get()` e o código segue por um caminho que parecia ser
o padrão.

Onze testes novos cobram isso de sete tabelas, e os onze foram **provados mordendo** —
removi uma chave de cada tabela, confirmei a reprovação, restaurei:

| Tabela | Universo | O que uma chave faltando causa |
|---|---|---|
| `_ACOES` | `ActionKind` | `UnknownActionError` na primeira automação do cliente que usar |
| `_OPERADORES` + `_compare` | `OPERATORS` | **decisão errada em silêncio** (ver abaixo) |
| `_CUSTOMER_FIELDS`, `_LAWSUIT_FIELDS`, `_ACCOUNT_FIELDS`, `_USER_FIELDS` | `VARIABLE_CATALOG` | `<mark>` no documento entregue ao cliente do escritório, sem erro |
| `_RESOLVERS` | namespaces do catálogo | `KeyError` que derruba a resolução INTEIRA |
| `_ROLE_ORDER`, `_ROLE_CAPABILITIES` | `UserRole` | usuário perde toda capacidade — e parece política |
| `_FINANCIAL_ORDER`, `_FINANCIAL_CAPABILITIES` | `FinancialAccess` | idem, na segunda dimensão da autorização |
| `_AGING_RANGES` | `AgingBucket` | faixa de inadimplência aparece zerada |
| `_EXPORT_COLUMNS` | `REPORT_KEYS` | relatório existe na tela e o export sai vazio |

Nenhuma estava divergente hoje. São catracas, não correções.

### O buraco silencioso que encontrei e NÃO consertei

`conditions.py::_compare` termina em `return bool(esquerda <= direita)`. Ou seja: **um
operador não reconhecido se comporta como `lte`**. Hoje `OPERATORS` declara nove e os nove
estão implementados, então não há defeito ativo. Mas acrescentar um décimo — um `contains`,
digamos — sem implementá-lo não levantaria erro nenhum: a automação passaria a decidir por
«menor ou igual» e ninguém saberia.

É o pior formato de bug do projeto: silencioso, em código de decisão, num produto que vende
prazo processual. **Não consertei porque consertar muda comportamento** e esta é uma spec
de refatoração — trocar o fallback por um erro explícito é mudança de regra, não de forma.
O teste `test_todo_operador_declarado_tem_implementacao` fecha o caminho por onde o defeito
entraria; o fallback em si fica para a 110 ou a 120.

### Uma exclusão legítima de tabela, documentada em vez de descoberta

`_ACOES` cobre 6 dos 7 valores de `ActionKind`. `LLM_DECISION` está fora de propósito:
`AutomationEngine.advance` a intercepta antes de chamar `run_action`, porque ela não produz
detalhe para registrar — escolhe o ramo e o laço segue (spec 094).

O teste não trata isso como tolerância genérica: a exclusão é uma constante nomeada
(`ACOES_TRATADAS_FORA_DA_TABELA`) com o motivo escrito ao lado. Uma **segunda** exclusão
precisa ser justificada por quem a acrescentar, em vez de caber num `>= 6` frouxo.

## 9. Definição de pronto

- [x] `PLR0912` no `select` — **em 8, não no default 12**, com o desvio justificado na §8
      (a 12 a regra não poderia disparar). Provado reprovando uma função de 10 ramos.
- [x] `ruff check . --select PLR0912` limpo, sem `noqa`
- [x] Tabelas de despacho exaustivas, com teste que prova — 11 testes sobre 13 tabelas,
      em `test_automations_dispatch.py`, `test_dispatch_tables.py` e
      `test_template_variables.py`, cada um provado mordendo
- [x] Nenhum teste anterior editado — os três arquivos são novos ou só receberam casos
- [x] Nenhuma linha de `app/` alterada: esta spec não teve o que refatorar
- [x] `make test` verde e wall-clock dentro do orçamento
- [x] `make lint` verde — repositório inteiro
- [x] `ROADMAP.md` com a linha da 111 em ✅
- [x] Commit `refactor(111): ramos demais`
