# 106 — Gate de complexidade ciclomática (C901, máx. 6)

**Fase:** 10 · **Tipo:** refatoração · **Orçamento:** +0 s (gate de lint, não de teste)
**Depende de:** 104 · **Status:** ✅ concluída

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

### A contagem estava errada, e para menos

A spec previu 41 funções em três cortes de 11 / +18 / +12. A medição no commit anterior
(`da213af`) deu **50** acima de 6, distribuídas em 10 / +12 / +28. O erro não foi de
método: foi de escala — a estimativa saiu de uma amostra, e a faixa 7–8 é justamente a
mais populosa, porque é onde uma função «normal» chega sem que ninguém ache que ela ficou
grande.

O degrau 3 encontrou **33** e não 28. A diferença são funções auxiliares criadas nos
degraus 1 e 2: com o gate em 8, uma extração que devolvia um helper de complexidade 7
passava. Descer o teto depois cobra esse resto. Vale como aviso para qualquer gate
descido em degraus: **cada degrau produz trabalho para o seguinte**, e a conta final é
maior que a soma das medições iniciais. No total, 55 funções foram simplificadas.

### Cada degrau achou um defeito de forma diferente

Não é a mesma refatoração feita três vezes com o número menor. Cada faixa tem uma doença
característica:

**Degrau 1 (acima de 10) — o preâmbulo e a fiação.** Funções longas onde o começo faz uma
coisa (montar, validar, preparar) e o resto faz outra, dentro de um laço. `_drive_iter`
tinha o prelúdio do grafo colado no laço que roda N vezes; extrair `_preparar_execucao`
não baixou só o número, deixou visível que aquilo acontece **uma vez**.

Quatro casos do mesmo padrão apareceram aqui, e é o mais traiçoeiro: **fábrica cuja
closure soma ramos**. `build`, `stream_thread`, `_fails_once` e `stream_message` são
funções curtas que devolvem outra função — e o McCabe cobra da externa a complexidade da
interna. Ler o código dá a impressão de que o medidor está errado; não está: quem lê
`build` precisa mesmo entender os dois níveis de uma vez.

**Degrau 2 (acima de 8) — duas regras no mesmo corpo.** A forma dominante é a validação
que confere coisas de naturezas diferentes em sequência (`_validate_shape` da financeira
validava transferência E lançamento simples), e a pilha de `except` que é, na verdade, um
mapa de erro para mensagem. `_handle_transaction_errors` virou `_MENSAGEM_POR_ERRO` mais
três linhas.

**Degrau 3 (acima de 6) — despacho por valor, em toda parte.** A forma esmagadoramente
mais comum: `if kind == A: ... elif kind == B: ...`. Vira tabela de despacho no nível do
módulo, e a tabela documenta o catálogo de um jeito que a cadeia de `elif` nunca fez.

Um detalhe que se repetiu três vezes e merece regra: **o fallback fica fora da tabela**.
Em `_handle_transaction_errors`, em `conditions.evaluate` e em `create_lawsuit`, o caso
«nenhum dos anteriores» não é mais um item do dicionário — é o `else` depois do `get`. Pôr
o padrão dentro da tabela faz o leitor procurar qual chave é o padrão; deixá-lo fora torna
óbvio que existe um, e qual é.

### O que NÃO cede: complexidade que é fluxo

Quatro funções reapareceram em todos os três degraus — `advance`, `_drive_iter`,
`stream_turn` e `_ask`. Elas não estavam mal organizadas; a complexidade delas **é o fluxo
de execução**: um laço de retry com quatro saídas, um driver de grafo, uma conversa com o
modelo que pode dar três voltas de ferramenta. Baixar o número nelas exigiu tirar uma
camada por degrau, e é exatamente isso que justifica o corte em três passos em vez de um
salto de 10 para 6.

O padrão que resolveu as quatro foi o mesmo: **união discriminada como valor de retorno**.
`_executar_passo` devolve `AutomationRun | None`, `_proximo_update` devolve
`tuple[...] | GraphResult | None`. Cada `continue` e cada `break` do laço original virou um
valor de retorno com nome e tipo — e o `isinstance` no chamador é o que faz o `mypy`
provar que todos os casos foram tratados. Tupla não serviria: obrigaria o valor do caminho
feliz a ser opcional em todo ponto de uso, e foi o `mypy` quem apontou isso.

Nenhuma precisou de `# noqa: C901`. **O projeto fecha a spec com zero silenciamentos**,
contra o teto de 3 que a regra 5 autorizava.

### O ganho maior não foi o número — foi a documentação

Extrair uma função obriga a nomeá-la, e nomear obriga a decidir o que ela é. Regras que
existiam só no fluxo do código e nunca tinham sido escritas passaram a estar escritas:

- **por que o `Retry-After` prevalece sobre o backoff** — e por que erro de transporte,
  que não tem cabeçalho para ler, cai no mesmo caminho (`_aguardar_retentativa`);
- **por que não se dorme depois da última tentativa** — seria segurar o chamador por um
  atraso que ninguém vai usar;
- **por que o custo só soma quando o provider informa** — `cost_usd` é `None` em modelo
  gratuito, e somar zero daria a impressão de que a conta foi medida (`_uso_somado`);
- **por que o erro que sobe é o do fallback, e não o primeiro** — é o último estado real
  da chamada (`_tentar_fallback`);
- **por que `_commit_usage` vem antes do `raise`** — a chamada que falhou é a que mais
  interessa auditar, e a sessão por request faria rollback dela;
- **por que a resposta do copiloto não é emitida dentro do laço** — ela só existe depois
  de `_persist_reply`, e emiti-la antes seria dizer que ficou pronta antes de estar
  gravada (`_eventos_do_progresso`);
- **por que a espera de `wait_until` não consome o passo** — `next_position` fica onde
  está, e é isso que faz aquilo ser espera e não pulo (`_marcar_espera`);
- **por que a análise guarda sugerido E corrigido** — saber que houve correção não diz
  nada sem saber de quê para quê, e é esse par que mede a qualidade da IA ao longo do
  tempo (`_correcoes_humanas`);
- **por que o cancelamento é checado ENTRE nós** — no meio de um nó poderia haver escrita
  em andamento (`_proximo_update`).

Nenhuma dessas frases é nova como decisão. Todas eram novas como texto.

### Cobrar os testes também foi acerto

Quatro funções de `tests/` estouraram o teto, três delas **meta-testes que guardam
gates**. Um teste ilegível é um gate em que ninguém confia, e a primeira reação a um gate
em que ninguém confia é afrouxá-lo. Se `tests/` tivesse ficado de fora do `select`, a
spec teria melhorado o `app/` e deixado exatamente a parte que vigia o `app/` sem vigia.

### Dois métodos que valeram, e um risco real

**Guardar os blocos antes e comparar byte a byte depois.** Usado em
`tabular_service.py::fetch`, que tinha 8 blocos quase iguais: salvei cada bloco antes,
comparei os 8 depois. Sete idênticos; o oitavo diferia só porque o `black` desdobrou um
ternário. Para extração em massa, é a única forma barata de provar que nada mudou.

**Diff de OpenAPI como prova de contrato.** Para qualquer refatoração que toque
`router.py`, dumpar o `app.openapi()` antes e depois e comparar. 311 caminhos, 384
operações, diff zero — verificado quatro vezes ao longo da spec. Um detalhe: o dump de
referência foi gravado com `ensure_ascii=True` e o novo sem, então o `diff` de texto
acusou 620 linhas de diferença que eram só escape de acento. Compare o JSON **parseado**,
não o texto.

**O risco: inserção posicional por script.** Errei três vezes, e duas vezes pelo mesmo
motivo — inseri o helper **entre o decorador e a função**. Em `extraction_router.py` o
FastAPI registrou o helper como rota e 11 arquivos de teste falharam na coleção; em
`publications/analysis.py` um `@dataclass(frozen=True)` passou a decorar uma função e o
`mypy` acusou 9 erros. Conferir depois não bastou: eu tinha escrito a regra e mesmo assim
verifiquei só «a linha anterior é a `def`», não «a linha anterior é um decorador».

A regra que resolve é mecânica, não de atenção — o script recua sozinho:

```python
inicio = idx_def
while inicio > 0 and linhas[inicio - 1].lstrip().startswith("@"):
    inicio -= 1
```

E, quando o helper não depende de ordem de definição, o lugar seguro é o **fim do
módulo** — sem posição para errar. Rodar `ruff` + `black` + `mypy` e os testes do módulo
depois de **cada** inserção é o que manteve o custo de cada erro em um minuto.

### Para a spec de `PLR0912`/`PLR0915`

Vai encontrar quase tudo pronto. `PLR0912` (ramos demais) mede quase a mesma coisa que o
`C901` e deve entrar praticamente verde. `PLR0915` (statements demais) é ortogonal: função
longa e linear — as que só montam um `dict` grande ou uma lista de colunas — não aparece
aqui e vai aparecer lá. As duas maiores candidatas que sobreviveram a esta spec inteira
sem serem tocadas são as que montam payload de resposta, não as que decidem.

## 10. Definição de pronto

- [x] `C90` no `select`, `max-complexity = 6` no `pyproject.toml`
- [x] `uv run ruff check .` sem nenhum C901 não silenciado
- [x] No máximo 3 `# noqa: C901`, cada um com justificativa, travados por meta-teste —
      **zero no projeto**; o teto e a exigência de justificativa foram provados nos dois
      sentidos (4 marcadores reprovam; 1 justificado passa)
- [x] Nenhum `per-file-ignores` novo
- [x] Nenhum teste anterior editado — nenhuma asserção tocada em nenhum dos três degraus
- [x] `make test` verde e wall-clock dentro do orçamento
- [x] `make lint` verde — repositório inteiro
- [x] `ROADMAP.md` com a linha da 106 em ✅
- [x] Commit `refactor(106): gate de complexidade ciclomática em 6` — em três, um por
      degrau (`7e982ac` teto 10, `3aaac51` teto 8, este teto 6)

---

## Nota de execução

41 funções é mais do que um ciclo do `/loop` fecha com folga, e o `CLAUDE.md` §8 é explícito:
se não fechar, **não marque como concluída**. O corte natural é por faixa de complexidade,
porque a faixa alta é onde mora o ganho e onde o risco de mudar comportamento é maior:

| Corte | Alvo | Previsto | Medido |
|---|---|---|---|
| 106 | `max-complexity = 10`, resolve a cauda | 11 | 10 |
| 106b | `max-complexity = 8` | +18 | +12 |
| 106c | `max-complexity = 6` | +12 | +33 |

(O `+33` do último degrau contra os 28 que sobravam da medição inicial é o resto que os
dois degraus anteriores produziram: com o gate em 8, um helper extraído com complexidade 7
passava. Ver §9.)

Cada corte é um `pyproject.toml` verde no fim. Descer o teto em três passos entrega gate
funcionando em todos eles — o que é melhor que uma spec grande que não fecha e deixa o
`select` sem `C90` por mais um ciclo.
