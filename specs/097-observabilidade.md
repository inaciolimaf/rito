# 097 — Observabilidade

**Fase:** 9 · **Tipo:** feature · **Orçamento:** +3 s
**Depende de:** 002 · **Status:** ⬜ pendente

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

*(preencher)*

## 10. Definição de pronto

Checklist padrão · Nenhum dado sensível em log · Trace atravessa o worker · Commit `feat(097): observabilidade`
