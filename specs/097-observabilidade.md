# 097 — Observabilidade

**Fase:** 9 · **Tipo:** feature · **Orçamento:** +3 s
**Depende de:** 002 · **Status:** ✅ concluída

---

## 1. Objetivo

Enxergar o sistema em produção: log estruturado correlacionado, tracing atravessando request e
worker, métricas e healthcheck que diz a verdade.

## 2. Escopo

- Log estruturado com `tenant_id`, `user_id`, `request_id`
- Tracing OpenTelemetry, incluindo tarefas Celery
- Métricas Prometheus
- Healthcheck raso e profundo
- Correlação entre request HTTP e task assíncrona
- Redação de dado sensível no log

## 3. Fora de escopo

- Backend de observabilidade (Grafana, Jaeger) — o Rito só exporta
- Alerta operacional (é do time de infra)

## 4. Modelo de dados

Nenhuma tabela nova.

## 5. Contratos de API

| Método | Rota | Autorização |
|---|---|---|
| GET | `/health` | público — liveness |
| GET | `/health/ready` | público — readiness (Postgres, Redis, S3) |
| GET | `/metrics` | interno — formato Prometheus |

## 6. Front-end

Nenhum.

## 7. Regras de negócio

1. Todo log é JSON com: `timestamp`, `level`, `message`, `request_id`, `tenant_id`, `user_id`, `route`, `duration_ms`.
2. `request_id` vem do header `X-Request-Id` ou é gerado; **propaga para as tasks Celery** — é o que permite seguir uma ação do clique até o worker.
3. **Redação obrigatória** no log: senha, token, chave de API, CPF, CNPJ, e-mail e telefone são mascarados. Teste verifica que nenhum deles aparece.
4. Trace por request, com spans de banco, chamada externa e LLM.
5. Task Celery continua o trace do request que a enfileirou.
6. Métricas: requisições por rota e status, latência p50/p95/p99, queries por request, tamanho das filas, tokens e custo de LLM, entregas de webhook, execuções de sincronização.
7. `/health` responde sem tocar em dependência — é liveness.
8. `/health/ready` verifica Postgres, Redis e S3 com timeout de 2 s cada; qualquer falha → 503 dizendo qual.
9. Log de erro inclui stack trace; log de request, não.
10. Nível ajustável por variável, sem redeploy.
11. Amostragem de trace configurável; padrão 10% em produção, 100% em erro.
12. Nenhum log em caminho quente que faça I/O síncrono.

## 8. Plano de testes

| Tipo | Caso | Custo |
|---|---|---|
| integração | log contém os 7 campos obrigatórios | ~0,3 s |
| integração | **`request_id` propaga para a task Celery** | ~0,4 s |
| integração | **senha, token e chave são redigidos** | ~0,3 s |
| integração | **CPF, e-mail e telefone são mascarados** | ~0,3 s |
| integração | trace tem spans de banco e de externa | ~0,3 s |
| integração | task continua o trace do request | ~0,4 s |
| integração | `/metrics` expõe as métricas esperadas | ~0,3 s |
| integração | `/health` não toca dependência | ~0,2 s |
| integração | `/health/ready` com Redis fora → 503 indicando | ~0,3 s |
| integração | erro loga stack; request, não | ~0,2 s |

**Total:** ~3,0 s

## 9. Descobertas

- **`BaseHTTPMiddleware` não enxerga o contexto da própria requisição.** O `call_next`
  do Starlette roda o resto da aplicação numa **task separada**, e task nova recebe uma
  *cópia* do contexto: o `tenant_id` que `get_current_user` publica e o contador de
  queries chegavam sempre vazios ao middleware. A regra 1 inteira depende de o
  middleware ler o que a rota escreveu, então o middleware virou ASGI puro — chama a
  aplicação com um `await` comum, na mesma task, e os dois lados compartilham o
  contexto. Foi a descoberta mais cara da spec e a única mudança estrutural que ela fez.
- **`ContextVar` não atravessa greenlet.** O SQLAlchemy async executa o driver dentro de
  um greenlet, que tem contexto próprio: um `query_count_var.set(n + 1)` no listener
  morria lá dentro e a métrica de queries por request saía zerada. O contexto passou a
  guardar um objeto **mutável** (`QueryCounter`) — mutar referência compartilhada é
  visível de qualquer contexto que a enxergue.
- **O template da rota não está onde parece.** Versões recentes do FastAPI montam os
  routers incluídos como sub-aplicações, e o `route.path_format` que chega ao scope é o
  do router — `/users/{user_id}`, sem o `/api/v1`. Rotular métrica assim juntaria rotas
  distintas de prefixos distintos. O template é reconstruído a partir do caminho concreto
  e dos `path_params`, que não dependem do formato interno do FastAPI.
- **"10% em produção, 100% em erro" é contraditório se lido ingenuamente.** A decisão de
  amostrar é tomada quando o span ABRE; o erro só se conhece quando ele FECHA. A saída
  foi separar gravar de exportar: o sampler devolve `RECORD_ONLY` para os 90% não
  sorteados (o span existe e recebe status, mas nasce sem a flag de exportação) e o
  processor exporta o que foi sorteado **ou** o que terminou em erro.
- **Varrer PII por formato nos campos estruturais criaria falso positivo.** Um UUID em
  cada cem tem 11 dígitos seguidos em algum lugar; sem bordas que excluam contexto
  hexadecimal, o `request_id` do log viraria `***` de vez em quando — o campo que existe
  para correlacionar perderia justamente essa serventia. A redação varre `message` e o
  `extra` do chamador; os campos que o próprio formatter monta são confiáveis por
  construção.
- **`Bearer` tem que ser mascarado antes da atribuição.** Em `Authorization: Bearer abc`,
  o padrão de `chave: valor` casa `Authorization: Bearer` e mascara **o esquema**,
  deixando o token intacto. A ordem das duas substituições é a correção.
- **O `/health` já era liveness correto e o `/health/ready` não checava o storage.** A
  sonda de S3 exigiu um `ping()` novo na interface `FileStorage`, não só na implementação:
  o healthcheck depende da abstração (CLAUDE.md §5), e trocar de storage não pode obrigar
  a mexer no healthcheck.
- **`scripts/run-tests.sh` apagava catálogo global semeado por migration.** `TRUNCATE ...
  CASCADE` esvazia a tabela referenciadora INTEIRA, não as linhas do tenant. Onde
  `tenant_id` é anulável — o NULO significando "global" —, isso levou junto os 19 agentes
  de sistema da 087, e a migration não os repõe porque já está aplicada. O efeito era 12
  testes da 087 falhando em toda execução SEGUINTE a um `make test`, o que faz o bug
  parecer intermitente quando é perfeitamente determinístico. A limpeza passou a
  preservar e repor as linhas sem tenant, descobrindo a lista pelo catálogo do Postgres
  em vez de por uma lista escrita à mão.
- **O orçamento de 300 s já estava quase esgotado antes desta spec.** Neste host de 4
  núcleos a suíte anterior à 097 mede 293 s, contra os 242 s registrados na última
  medição do `test-timing.json`. O cap de 2 workers do pytest vinha da 035, quando o
  backend levava ~85 s e as três suítes eram comparáveis; hoje o backend é o poste mais
  alto por larga margem e as outras duas devolvem seus núcleos nos primeiros 90 s. O cap
  subiu para 3 com medição — não é folga comprada, é uma constante de tuning que ficou
  velha. A 098 é quem tem escopo para atacar o custo de verdade.
- **O span por query custa menos do que parece.** A hipótese era que criar um objeto de
  span por `SELECT` dominaria o custo da spec; medido em A/B sobre 69 testes de
  integração, a diferença ficou dentro do ruído (18,5 s contra 19,2 s). A regra 4 ficou
  incondicional em vez de depender de haver coletor configurado.
- **`tests/integration/test_health.py` foi absorvido.** Os quatro casos dele viraram
  cinco em `test_observability.py`, junto com o resto da regra 8 — manter os dois seria
  duas descrições concorrentes do mesmo endpoint, e a que ficou é a que conhece o
  storage e o teto de 2 s.

## 10. Definição de pronto

- [x] Escopo implementado, nada além
- [x] Todas as 12 regras de negócio com teste
- [x] Nenhum dado sensível em log — senha, token, chave, CPF, CNPJ, e-mail e telefone
- [x] Trace atravessa o worker — `traceparent` W3C nos headers da task
- [x] `make test` verde: 1409 backend + 279 frontend + 10 e2e
- [x] `make lint` verde: ruff, black, mypy strict, eslint, tsc
- [x] Sem `Any`, `as any` ou `# type: ignore` sem justificativa em comentário
- [x] `ROADMAP.md` atualizado para ✅
- [x] Commit `feat(097): observabilidade`
