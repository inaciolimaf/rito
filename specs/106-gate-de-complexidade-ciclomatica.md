# 106 — Gate de complexidade ciclomática (C901, máx. 6)

**Fase:** 10 · **Tipo:** refatoração · **Orçamento:** +0 s (gate de lint, não de teste)
**Depende de:** 104 · **Status:** ⬜ pendente

---

## 1. Objetivo

Ligar o gate de complexidade ciclomática do Ruff em **6** e trazer as 41 funções que hoje
passam desse teto para dentro dele. Complexidade ciclomática é o número de caminhos
independentes por função — é o proxy mais direto de «quantos casos alguém precisa segurar na
cabeça para revisar isto», e é a métrica que o `CLAUDE.md` §8 pede implicitamente ao mandar a
spec de refatoração procurar «violação de SOLID» sem dar um instrumento para achá-la.

> Refatoração: **nenhuma mudança de comportamento**. Os testes das specs originais de cada
> função passam sem edição — é esse o critério que separa «extraí uma função auxiliar» de
> «reescrevi a regra».

## 2. Escopo

`pyproject.toml`, `[tool.ruff.lint]`:

```toml
select = ["E", "F", "I", "UP", "B", "SIM", "C90"]

[tool.ruff.lint.mccabe]
max-complexity = 6
```

Medido em 28/08/2026, commit `44469bd`: **41 funções** acima de 6. Distribuição —
12 em 7, 10 em 8, 8 em 9, 1 em 10, 3 em 11, 3 em 14, e a cauda longa de 15, 18, 20 e 23.

| Arquivo:linha | Função | Cx |
|---|---|---|
| `domain/lawsuits/listing.py:216` | `_build_conditions` | 23 |
| `domain/templates/variables.py:138` | `_resolve_lawsuit` | 20 |
| `domain/templates/variables.py:95` | `_resolve_customer` | 18 |
| `integrations/http/client.py:118` | `_request_com_resiliencia` | 15 |
| `domain/lawsuits/cnj.py:120` | `infer_court_code` | 14 |
| `domain/automations/engine.py:171` | `advance` | 14 |
| `ai/graphs/base_agent.py:84` | `build` | 14 |
| `domain/financial/service.py:722` | `update_series` | 11 |
| `domain/financial/repository.py:217` | `_filter_conditions` | 11 |
| `ai/runtime.py:149` | `_drive_iter` | 11 |
| `domain/ai/sql_guard.py:82` | `check_sql` | 10 |
| `domain/webhooks/ssrf.py:31` | `validate_webhook_url` | 9 |
| `domain/templates/resolve.py:50` | `_build_scope` | 9 |
| `domain/reports/tabular_service.py:81` | `fetch` | 9 |
| `domain/financial/service.py:500` | `_validate_references` | 9 |
| `domain/customers/repository.py:63` | `_build_filters` | 9 |
| `domain/automations/decision.py:211` | `_ask` | 9 |
| `domain/ai/service.py:171` | `run` | 9 |
| `ai/tools/read_analytics.py:129` | `list_taxonomies` | 9 |
| `domain/templates/variables.py:184` | `_resolve_escritorio` | 8 |
| `domain/posts/repository.py:38` | `search` | 8 |
| `domain/notifications/dispatch.py:36` | `dispatch` | 8 |
| `domain/monitored_terms/schemas.py:23` | `validate_by_kind` | 8 |
| `domain/financial/schemas.py:184` | `_validate_shape` | 8 |
| `domain/documents/extraction.py:217` | `read_text` | 8 |
| `domain/automations/decision.py:69` | `validate_decision_config` | 8 |
| `domain/automations/actions.py:42` | `run_action` | 8 |
| `domain/ai/threads_router.py:245` | `stream_thread` | 8 |
| `domain/ai/copilot.py:185` | `stream_turn` | 8 |
| `integrations/openrouter/client.py:134` | `parse_stream_line` | 7 |
| `domain/webhooks/sender.py:59` | `send` | 7 |
| `domain/schedule/service.py:81` | `list_events` | 7 |
| `domain/publications/analysis.py:214` | `review` | 7 |
| `domain/lawsuits/workflow_service.py:118` | `undo` | 7 |
| `domain/lawsuits/router.py:357` | `create_lawsuit` | 7 |
| `domain/documents/extraction_router.py:100` | `extract_document` | 7 |
| `domain/datajud/movement_sync_service.py:170` | `_sync_lawsuit_inner` | 7 |
| `domain/automations/service.py:185` | `_validate` | 7 |
| `domain/automations/engine.py:285` | `_wait_for` | 7 |
| `domain/automations/conditions.py:30` | `evaluate` | 7 |
| `core/bootstrap.py:57` | `validate` | 7 |

## 3. Fora de escopo

- `PLR0911`, `PLR0912`, `PLR0915` — cada uma tem spec própria (112, 111, 109). Há sobreposição
  de alvos e isso é proposital: baixar a complexidade de `_build_conditions` provavelmente
  resolve o `PLR0912` dele também. Quem chegar primeiro colhe; a spec seguinte reconta.
- Tamanho de função em linhas. Correlaciona, mas não é a mesma métrica, e não entra aqui.
- Complexidade no frontend (`eslint complexity`). Spec futura.
- Reescrever regra de negócio. Se uma função só cabe em 6 mudando o que ela decide, **ela não
  entra nesta spec** — registre em `## 9. Descobertas` e deixe o `# noqa: C901` com
  justificativa, conforme a regra 4.

## 4. Modelo de dados

Nenhuma tabela, nenhuma migration.

## 5. Contratos de API / Front-end

Nada muda. Cinco das 41 funções são handlers de rota (`create_lawsuit`, `extract_document`,
`stream_thread`, `stream_turn`, `list_taxonomies`) — a assinatura, o `response_model` e o
status de cada uma continuam idênticos.

## 6. Estratégia de correção

Três formas, nesta ordem de preferência:

1. **Extrair função auxiliar nomeada.** O caso comum. `_build_conditions` (23) e
   `_filter_conditions` (11) são cadeias de `if filtro is not None: condições.append(...)` —
   viram um mapa declarativo de campo → construtor de condição, o que também apaga a
   duplicação entre os dois.
2. **Tabela de despacho.** `run_action` (8), `evaluate` (8), `validate_by_kind` (8) e
   `infer_court_code` (14) são `if/elif` sobre um enum. Um `dict[Enum, Callable]` derruba a
   complexidade para 1–2 e torna «esqueceram de tratar um valor novo do enum» um erro de
   mypy em vez de um `else` silencioso.
3. **Cláusula de guarda.** `validate_webhook_url` (9) e `check_sql` (10) já são sequências de
   validação; separar cada regra em sua própria função pequena mantém a leitura e some com o
   aninhamento.

`_resolve_customer` (18), `_resolve_lawsuit` (20) e `_resolve_escritorio` (8) são o mesmo
padrão três vezes — resolvedor de variável de modelo por nome. Os três juntos são candidatos
naturais a um registro `dict[str, Resolver]`, o que é a regra dos 3 usos do §6 aplicada ao
backend.

## 7. Regras de negócio

1. `C90` entra no `select` do Ruff com `max-complexity = 6`. Não é aviso: `make lint` reprova.
2. Nenhuma das 41 correções muda comportamento observável. O teste da spec original de cada
   função passa **sem edição**. Essa é a definição operacional de «refatoração» aqui.
3. Toda função auxiliar extraída é privada (`_nome`) e tipada — `mypy --strict` continua verde
   sem exceção nova.
4. `# noqa: C901` é permitido, mas **sempre com justificativa em comentário na linha de
   cima**, e a justificativa não pode ser «é complexo mesmo». O `test_final_audit.py` já exige
   isso de `# type: ignore`; esta spec estende a mesma exigência ao `noqa`, no mesmo teste.
5. O teto de `# noqa: C901` no projeto é **3**. Meta-teste trava o número, no mesmo formato do
   teto de `slow` da 009. Se a implementação precisar do quarto, a spec não fecha — significa
   que o `max-complexity` escolhido está errado e a conversa é outra.
6. Nenhum arquivo entra em `per-file-ignores` por causa desta spec. Silenciar por arquivo
   esconde as funções que ainda não foram tocadas.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| meta | no máximo 3 `# noqa: C901` no projeto, todos justificados | `tests/meta/test_final_audit.py` (estende) | ~0,1 s |
| meta | todo `# noqa` do projeto tem justificativa na linha acima | `tests/meta/test_final_audit.py` (estende) | ~0,2 s |
| — | os testes das specs de origem das 41 funções passam **sem edição** | — | — |

**Total estimado:** +0,3 s
**Fixtures externas:** nenhuma.

O gate de verdade desta spec não é um teste: é o `make lint` do CI, que já roda em todo PR.

## 9. Descobertas

Preencher durante a implementação. Em especial: funções que não couberam em 6 sem mudar
regra, e o que a spec de `PLR0912`/`PLR0915` vai encontrar já resolvido.

## 10. Definição de pronto

- [ ] `C90` no `select`, `max-complexity = 6` no `pyproject.toml`
- [ ] `uv run ruff check .` sem nenhum C901 não silenciado
- [ ] No máximo 3 `# noqa: C901`, cada um com justificativa, travados por meta-teste
- [ ] Nenhum `per-file-ignores` novo
- [ ] Nenhum teste anterior editado
- [ ] `make test` verde e wall-clock dentro do orçamento
- [ ] `make lint` verde — repositório inteiro
- [ ] `ROADMAP.md` com a linha da 106 em ✅
- [ ] Commit `refactor(106): gate de complexidade ciclomática em 6`

---

## Nota de execução

41 funções é mais do que um ciclo do `/loop` fecha com folga, e o `CLAUDE.md` §8 é explícito:
se não fechar, **não marque como concluída**. O corte natural é por faixa de complexidade,
porque a faixa alta é onde mora o ganho e onde o risco de mudar comportamento é maior:

| Corte | Alvo | Funções |
|---|---|---|
| 106 | `max-complexity = 10`, resolve a cauda | 11 |
| 106b | `max-complexity = 8` | +18 |
| 106c | `max-complexity = 6` | +12 |

Cada corte é um `pyproject.toml` verde no fim. Descer o teto em três passos entrega gate
funcionando em todos eles — o que é melhor que uma spec grande que não fecha e deixa o
`select` sem `C90` por mais um ciclo.
