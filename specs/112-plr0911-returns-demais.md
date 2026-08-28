# 112 — PLR0911: returns demais

**Fase:** 11 · **Tipo:** refatoração · **Orçamento:** +0 s (gate de lint)
**Depende de:** 106, 111 · **Status:** ⬜ pendente

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

Preencher durante a implementação.

## 9. Definição de pronto

- [ ] `PLR0911` no `select`, teto default
- [ ] `ruff check . --select PLR0911` limpo, sem `noqa`
- [ ] Os três resolvedores de `variables.py` unificados num registro
- [ ] Nenhum teste anterior editado
- [ ] `make test` verde e wall-clock dentro do orçamento
- [ ] `make lint` verde — repositório inteiro
- [ ] `ROADMAP.md` com a linha da 112 em ✅
- [ ] Commit `refactor(112): returns demais`
