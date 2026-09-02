# 112 — PLR0911: returns demais

**Fase:** 11 · **Tipo:** refatoração · **Orçamento:** +0 s (gate de lint)
**Depende de:** 106, 111 · **Status:** ✅ concluída

---

## 1. Objetivo

Ligar `PLR0911` (too-many-return-statements) e resolver as sete funções acima do teto. Muitos
pontos de saída não são um problema de estilo: são o motivo pelo qual ninguém consegue afirmar
o que uma função devolve sem ler todos os seus ramos até o fim.

> Refatoração: nenhuma mudança de comportamento.

## 2. Escopo

`pyproject.toml`: `select` ganha `PLR0911`. Teto default do Ruff: **6 returns**. Manter.

Medido em 28/08/2026, commit `44469bd`, sobre `ruff check .`: **7 violações**.

| Arquivo:linha | Função | Returns |
|---|---|---|
| `app/domain/templates/variables.py:138` | `_resolve_lawsuit` | 20 |
| `app/domain/templates/variables.py:95` | `_resolve_customer` | 18 |
| `app/domain/lawsuits/cnj.py:120` | `infer_court_code` | 14 |
| `app/domain/reports/tabular_service.py:81` | `fetch` | 9 |
| `app/domain/templates/variables.py:184` | `_resolve_escritorio` | 8 |
| `app/domain/automations/conditions.py:30` | `evaluate` | 7 |
| `app/integrations/openrouter/client.py:134` | `parse_stream_line` | 7 |

## 3. Leitura do inventário

**Três das sete são o mesmo arquivo** — `templates/variables.py`, com `_resolve_customer`
(18), `_resolve_lawsuit` (20) e `_resolve_escritorio` (8). São três resolvedores de variável
de modelo com a mesma forma: uma cadeia de `if nome == "x": return ...`. Isso é a regra dos
3 usos do `CLAUDE.md` §6 gritando: o padrão apareceu três vezes, ele quer virar um registro
`dict[str, Resolver]` com uma função de lookup só. As três somem juntas, e a 111 já aponta
para a mesma correção.

`infer_court_code` (14) e `evaluate` (7) são despacho por enum — mesma correção da 111.

`fetch` (9) é diferente: é a função de 189 linhas de `tabular_service`, e os returns ali são
saídas antecipadas de validação. A saída é cláusula de guarda extraída, não tabela.

`parse_stream_line` (7) é um parser de SSE: cada `return` é um formato de linha reconhecido.
É o caso mais legítimo dos sete — e mesmo assim cabe em 6 separando «linha de controle» de
«linha de dado» em duas funções.

## 4. Fora de escopo

- Reduzir `fetch` de 189 linhas para um tamanho decente. Isso é `PLR0915`/`C901` (specs 109 e
  106); aqui só os pontos de saída.
- O protocolo SSE do OpenRouter.

## 5. Modelo de dados / API / Front-end

Nada.

## 6. Regras de negócio

1. `PLR0911` no `select`, teto default de 6.
2. Nenhuma mudança de comportamento.
3. Os três resolvedores de `variables.py` viram **um** registro por nome. Nenhum nome de
   variável de modelo some ou muda de formato — os testes da spec 066 provam isso sem edição.
4. Nenhum `# noqa: PLR0911`.
5. Recontar depois da 106 e da 111.

## 7. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| unit | o registro de resolvedores cobre exatamente os nomes que a API `/api/v1/template-variables` publica | `tests/unit/test_template_variables.py` (estende) | ~0,1 s |
| — | testes das specs 066, 026 e 041 passam sem edição | — | — |

**Total estimado:** +0,1 s

## 8. Descobertas

### As sete já estavam resolvidas — a §3 acertou o diagnóstico e a 106 aplicou a cura

Recontagem sobre `eef43a7` (fechamento da 111): **zero violações a 6**. A §3 previu que os
três resolvedores de `variables.py` virariam «um registro `dict[str, Resolver]` com uma
função de lookup só», e é exatamente o que a 106 fez ao atacar a complexidade ciclomática
deles — `_CUSTOMER_FIELDS`, `_LAWSUIT_FIELDS`, `_ACCOUNT_FIELDS` e `_USER_FIELDS` são esse
registro. `infer_court_code` virou `_SEGMENTOS`, `evaluate` virou `_OPERADORES`, `fetch`
ganhou as cláusulas de guarda extraídas e `parse_stream_line` foi separada.

Sete diagnósticos, sete curas, nenhuma delas aplicada por esta spec. Vale como validação do
método de degraus da 106: atacar a dimensão certa (complexidade) resolveu as outras três
(volume, ramificação, saídas) de carona.

### Este gate está DOMINADO pelo `C901` — e a medição diz isso, não a intuição

Baixando o teto experimentalmente para 5, cinco funções aparecem. As cinco têm complexidade
ciclomática **exatamente 6**: `cli.main`, `redaction.redact_value`,
`analytics.next_best_action`, `engine._executar_passo` e `recurrence_service.generate_next`.

Isso não é coincidência: um `return` a mais quase sempre custa um `if` a mais. O sétimo
`return` empurraria a complexidade para 7 e seria barrado pelo gate da 106 **antes** de
chegar aqui. Tentei construir uma função que violasse `PLR0911(6)` e passasse no
`C901(6)` — com `match`, com `try`/`except` encadeado, com `with` — e não consegui.

Diferença importante em relação à 111: lá, `PLR0912` mede algo que o `C901` não vê (o `else`
é ramo e não é decisão), e a prova estava no próprio código. Aqui não há tal caso. **O gate
entra como seguro, não como restrição ativa** — custa zero, e continua valendo se algum dia
aparecer construção que multiplique saídas sem custar decisão.

### Descer para 5 foi considerado e recusado

Seria a única forma de tornar a regra ativa hoje, e o preço é ruim: as cinco funções teriam
que trocar cláusula de guarda por variável de resultado e saída única. Isso é **pior** — e é
o oposto do que a §9 da 106 concluiu, onde extrair guardas foi justamente uma das correções
que melhoraram a leitura.

Um gate que só morde forçando estilo pior não deve morder. Fica em 6, com a razão escrita no
`pyproject.toml` para que ninguém «conserte» a folga depois.

### O teste da §7 fecha um circuito que os da 111 deixaram aberto

A 111 já comparava os quatro mapas de campo com `VARIABLE_CATALOG` nos dois sentidos. Faltava
a ponta de fora: `build_variable_map` é quem de fato produz as chaves que o modelo usa, e
nada garantia que ela concordasse com as tabelas — ela poderia filtrar, prefixar ou pular.

O teste novo a chama de verdade, com um escopo vazio e um `User` em memória (sem banco), e
compara o conjunto de chaves com o que `/api/v1/template-variables` publica. É a ligação que
o usuário faz quando arrasta uma variável do seletor para dentro do modelo, e agora ela está
provada de ponta a ponta sem custar uma query.

### Nota de método: gate verde não é spec vazia

Três specs seguidas (109, 111, 112) chegaram com o gate já verde por causa da 106. A
tentação é ligar a regra e fechar. O que deu valor nas três foi perguntar **o que a regra
protege que hoje nada protege** — e a resposta foi diferente em cada uma: na 109, a ordem de
registro de rotas e middleware; na 111, a exaustividade das tabelas que a 106 criou; aqui, a
ligação entre o catálogo publicado e o mapa realmente produzido.

## 9. Definição de pronto

- [x] `PLR0911` no `select`, teto default de 6, com a folga justificada na §8
- [x] `ruff check . --select PLR0911` limpo, sem `noqa`
- [x] Os três resolvedores de `variables.py` unificados num registro — **feito pela 106**;
      esta spec confirmou e cobriu com teste
- [x] Nenhum teste anterior editado
- [x] Nenhuma linha de `app/` alterada
- [x] `make test` verde e wall-clock dentro do orçamento
- [x] `make lint` verde — repositório inteiro
- [x] `ROADMAP.md` com a linha da 112 em ✅
- [x] Commit `refactor(112): returns demais`
