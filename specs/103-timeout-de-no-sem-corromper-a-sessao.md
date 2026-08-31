# 103 — Timeout de nó sem corromper a sessão (Bloco D da 101)

**Fase:** 10 · **Tipo:** correção · **Orçamento:** +2 s no wall-clock
**Depende de:** 082, 085, 090, 101 · **Status:** ✅ concluída

---

## 1. Objetivo

Fechar a dívida técnica nº 21. Quando o timeout por nó (regra 5 da 082) corta a execução
**dentro de uma query**, o cancelamento invalida a conexão do asyncpg e a sessão de quem
chamou para de escrever — inclusive o passo de erro que existe exatamente para registrar
esse timeout. O resultado prático era o pior possível: a execução que estourou o tempo não
conseguia registrar que estourou o tempo, e o thread ficava eternamente `running`.

Depois desta spec: o passo de erro é gravado por uma conexão própria, o thread termina em
`error` e a requisição devolve **503** em vez de morrer calada.

## 2. Escopo

- `GraphRuntime._fail` tenta escrever pela sessão de quem chamou (caminho normal,
  inalterado) e, quando essa escrita falha, grava o passo de erro, o checkpoint e o
  `status = error` por uma sessão que o runtime abre, comita e fecha.
- `RuntimeSessionLostError`: o runtime passa a **dizer** que a transação de quem chamou
  morreu, em vez de devolver um `GraphResult` como se nada tivesse acontecido.
- `create_durable_thread`: `POST /ai/threads` com `autorun=true` e a conversa nova do
  copiloto criam o thread numa transação própria, que commita **antes** de a execução
  começar.
- Tradução nas rotas: 503 em `POST /ai/threads`, `POST /ai/threads/{id}/resume` e
  `POST /ai/copilot/message`; evento `error` + `rollback` explícito nos dois SSE.
- O teste que a dívida guardava como "reprodução" (`pg_sleep` na sessão do runtime).

## 3. Fora de escopo

- **Commit por passo.** Os passos anteriores ao timeout continuam sumindo com o `rollback`
  da requisição. Fica registrado como a **dívida nº 27**, spec-alvo 125 — é mudança de
  semântica de transação do runtime e precisa do seu ciclo.
- **Mover o timeout para a fronteira de I/O.** Era o caminho preferido na análise da
  tentativa anterior e foi **medido inviável** aqui — ver §9.
- **Fazer a requisição sobreviver.** Ela não sobrevive: a conexão morreu. O que esta spec
  entrega é que ela morra dizendo o quê, com o registro já durável.
- **`ai_messages` do copiloto** perdidas no mesmo `rollback` — mesma família da nº 27.
- Qualquer mudança em `get_session_for_current_user`, que continua sendo o dono da
  transação das rotas de domínio.

## 4. Modelo de dados

Nenhuma tabela nova, nenhuma coluna nova, nenhuma migration. A sessão de registro escreve
nas mesmas `ai_steps`, `ai_checkpoints` e `ai_threads` da 082 — e seta `app.tenant_id`
como qualquer outra sessão, senão o RLS barraria o `INSERT` (é o que a regra 6 abaixo
prova).

## 5. Contratos de API

| Método | Rota | Entrada | Saída | Autorização |
|---|---|---|---|---|
| POST | `/api/v1/ai/threads` | `autorun=true` | `503` quando o nó estoura o tempo dentro de uma query | COLABORADOR |
| POST | `/api/v1/ai/threads/{id}/resume` | — | `503` no mesmo caso | COLABORADOR |
| POST | `/api/v1/ai/copilot/message` | — | `503` no mesmo caso | COLABORADOR |
| GET | `/api/v1/ai/threads/{id}/stream` | — | `200` + `event: error` | COLABORADOR |
| GET | `/api/v1/ai/copilot/stream/{id}` | — | `200` + `event: error` | COLABORADOR |

Nenhum contrato existente mudou de forma: o 503 é um estado novo de um caminho que antes
devolvia 500 sem registro. Erros em RFC 7807, como o resto da API.

## 6. Front-end

Nada. Nenhum componente novo, nenhuma rota nova. O painel já trata `status = "error"` e o
evento `error` do SSE desde a 085 — o que muda é que agora eles chegam.

## 7. Regras de negócio

1. **O registro da falha não depende da sessão que falhou.** Se a escrita do passo de erro
   pela sessão de quem chamou levantar `SQLAlchemyError`, o runtime grava o passo, o
   checkpoint e o `status = error` por uma sessão própria, que commita sozinha.
2. **A sessão própria respeita o tenant.** Ela seta `app.tenant_id` antes de escrever; o
   registro de um tenant não aparece para outro.
3. **A falha do registro fora de banda não mascara a falha original.** Se nem a sessão
   própria conseguir escrever, o motivo vai para o log com `logger.exception` e o erro que
   sobe continua sendo o do timeout.
4. **O runtime não dá `rollback` na transação dos outros.** Ele levanta
   `RuntimeSessionLostError`; quem abriu a transação é quem a desfaz.
5. **Quem vai rodar existe antes de rodar.** `autorun` e conversa nova do copiloto criam o
   thread numa transação própria já comitada — uma conexão nova não enxerga linha não
   comitada, e sem isso a regra 1 não teria onde escrever.
6. **O thread sobrevive ao `rollback` da requisição.** Depois do 503, ele continua lá, em
   `error`, com o motivo — antes, sumia junto com a transação.
7. **O SSE conta em vez de cortar.** Com a resposta já começada não cabe 503: o cliente
   recebe `event: error` e a conexão volta ao pool pelo `rollback` de quem a abriu.
8. **O caminho feliz não mudou.** Nenhum teste da 082 foi editado.

## 8. Plano de testes

| Tipo | Caso | Arquivo | Custo |
|---|---|---|---|
| integração | timeout dentro de query grava o passo de erro e o thread termina em `error` (regras 1, 4) | `tests/integration/test_ai_runtime_timeout.py` | 0,42 s |
| RLS | o registro fora de banda não vaza para outro tenant (regra 2) | idem | 0,43 s |
| integração | `autorun` devolve 503 e o thread sobrevive com o erro (regras 5, 6) | idem | 0,80 s |
| integração | o SSE conta a falha ao cliente (regra 7) | idem | 0,42 s |
| integração | conversa nova do copiloto é comitada antes de rodar (regra 5) | idem | 0,08 s |
| regressão | os 21 testes da 082 e o contrato de grafos da 090 (regra 8) | `test_ai_threads.py`, `test_graph_contract.py` | — |

**Total medido:** 3,7 s no arquivo isolado (1,2 s são o `lifespan` do cliente HTTP, pago
uma vez); **+2 s** no wall-clock da suíte, que absorve o resto em paralelo.
**Fixtures externas:** nenhuma. Nenhuma chamada de LLM — o grafo lento é determinístico e
o provider do teste do copiloto levanta `AssertionError` se alguém tentar usá-lo.

## 9. Descobertas

**O `wait_for` não podia sair.** A lista de caminhos viáveis que a tentativa anterior
deixou registrada punha em primeiro lugar "mover o timeout para a fronteira de I/O que é
segura de cancelar — a chamada HTTP ao modelo". Medido aqui: não serve sozinho. O
`test_hangs` da 082 é um nó que trava num `asyncio.Event().wait()`, sem tocar em banco nem
em modelo; sem o watchdog genérico ele volta a pendurar a execução para sempre, e o teste
da regra 5 falharia. O `wait_for` continua onde estava. O que mudou é que o registro da
falha deixou de depender da vítima dele.

**Ler o objeto depois da escrita falhada também morre.** Uma primeira versão passava o
`AiThread` para o registro fora de banda e lia `thread.id` lá dentro. Um `flush` que falha
expira o objeto, e ler qualquer atributo dispara um carregamento preguiçoso — na sessão
que acabou de morrer. O `id` e o `step` são lidos **antes** da tentativa de escrita, e o
registro fora de banda recebe valores, não o objeto.

**O `rollback` de dentro do `session.begin()` funciona, mas só se ninguém tocar em nada
depois.** A tentativa anterior registrou `InvalidRequestError: Can't operate on closed
transaction inside context manager` e concluiu que o `rollback` de dentro é impossível.
Medido de novo: o `rollback` em si passa; o que quebra é a **próxima** leitura de um objeto
expirado dentro do mesmo contexto. É por isso que a regra 4 existe — o SSE, que é o único
lugar onde o `rollback` acontece de dentro, o faz como última instrução antes de fechar o
gerador.

**O `autorun` era o caso pior, e virou o caso testado.** Criar e executar na mesma
transação não é um detalhe de implementação: é o que tornava a dívida irrecuperável, porque
nenhuma outra conexão enxerga uma linha não comitada. `create_durable_thread` tem um efeito
colateral desejado — se o resto da requisição falhar, o thread continua lá, com o motivo.
Antes, a execução sumia junto e o usuário ficava sem nada para olhar.

**Resíduo numerado.** Os passos anteriores ao timeout somem no `rollback` da requisição:
`ai_steps` fica com um passo de erro numerado 3 e sem os passos 1 e 2. Vira a **dívida nº
27** (spec-alvo 125), e é o "commit por passo" que a análise do item 21 já listava.

**O comentário de contorno da 092 foi atualizado, não removido.** O
`test_todo_grafo_respeita_o_timeout_de_no` continua com `node_timeout_s=1.0` porque o que
ele cobra é outra coisa (todo grafo registrado respeita o teto); o comentário que explicava
o número deixou de dizer que a sessão fica inutilizável sem saída e passa a apontar para o
arquivo onde esse caminho é testado.

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as regras de negócio com teste
- [x] Teste de isolamento por tenant (regra 2 — a sessão nova é uma superfície de RLS nova)
- [x] `make test` verde e wall-clock dentro do orçamento
- [x] `make lint` verde
- [x] Sem `Any`, `as any`, `# type: ignore` sem justificativa em comentário
- [x] Nenhum teste da 082 editado
- [x] `docs/DIVIDA-TECNICA.md`: item 21 fechado, item 27 aberto com alvo
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `fix(103): timeout de nó sem corromper a sessão`
