# 111 — PLR0912: ramos demais

**Fase:** 11 · **Tipo:** refatoração · **Orçamento:** +0 s (gate de lint)
**Depende de:** 106, 109 · **Status:** ⬜ pendente

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

Preencher durante a implementação.

## 9. Definição de pronto

- [ ] `PLR0912` no `select`, teto default
- [ ] `ruff check . --select PLR0912` limpo, sem `noqa`
- [ ] Tabelas de despacho exaustivas, com teste que prova
- [ ] Nenhum teste anterior editado
- [ ] `make test` verde e wall-clock dentro do orçamento
- [ ] `make lint` verde — repositório inteiro
- [ ] `ROADMAP.md` com a linha da 111 em ✅
- [ ] Commit `refactor(111): ramos demais`
