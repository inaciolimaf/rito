# 109 — PLR0915: funções com corpo longo demais

**Fase:** 10 · **Tipo:** refatoração · **Orçamento:** +0 s (gate de lint)
**Depende de:** 106 · **Status:** ⬜ pendente

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
- `max-lines-per-function` no ESLint. Spec futura.
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

Preencher durante a implementação — em especial, quantas das 4 já estavam resolvidas pela 106.

## 9. Definição de pronto

- [ ] `PLR0915` no `select`, teto default
- [ ] `ruff check . --select PLR0915` limpo, sem `noqa`
- [ ] Meta-teste de ordem de middleware e inventário de rotas, verde
- [ ] Nenhum teste anterior editado
- [ ] `make test` verde e wall-clock dentro do orçamento
- [ ] `make lint` verde — repositório inteiro
- [ ] `ROADMAP.md` com a linha da 109 em ✅
- [ ] Commit `refactor(109): funções longas demais`
