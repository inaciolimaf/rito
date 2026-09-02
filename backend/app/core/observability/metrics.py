"""Métricas Prometheus (spec 097, regra 6).

Um registry só, montado uma vez por processo, com as sete famílias que a regra 6 pede.
As métricas de HTTP são alimentadas pelo middleware; as de domínio (LLM, webhook,
sincronização) por quem executa a ação, através das funções `record_*` abaixo — nenhum
service importa `prometheus_client` direto (CLAUDE.md §5, DIP).

O rótulo de rota é sempre o **template** (`/api/v1/lawsuits/{lawsuit_id}`), nunca o
caminho concreto: rotular por caminho criaria uma série temporal por processo do
escritório e derrubaria o Prometheus em uma semana.
"""

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from prometheus_client.core import CollectorRegistry as _Registry
from sqlalchemy import event

from app.core.observability.context import count_query, current_query_count

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncEngine

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

REGISTRY: _Registry = CollectorRegistry()

# Buckets em segundos cobrindo as metas de p95 da 098 (200 ms a 500 ms) com resolução
# suficiente logo abaixo e acima delas — o p95 calculado pelo Prometheus interpola
# dentro do bucket, então bucket largo na faixa que interessa é p95 mentiroso.
_LATENCY_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 2.5, 5.0, 10.0)

http_requests_total = Counter(
    "rito_http_requests_total",
    "Requisições HTTP concluídas.",
    ["method", "route", "status"],
    registry=REGISTRY,
)

http_request_duration_seconds = Histogram(
    "rito_http_request_duration_seconds",
    "Latência das requisições HTTP (p50/p95/p99 pelo histograma).",
    ["method", "route"],
    buckets=_LATENCY_BUCKETS,
    registry=REGISTRY,
)

http_queries_per_request = Histogram(
    "rito_http_queries_per_request",
    "Queries ao Postgres por requisição.",
    ["route"],
    buckets=(1, 2, 3, 5, 8, 13, 21, 34, 55, 89),
    registry=REGISTRY,
)

celery_queue_depth = Gauge(
    "rito_celery_queue_depth",
    "Tarefas aguardando na fila.",
    ["queue"],
    registry=REGISTRY,
)

llm_tokens_total = Counter(
    "rito_llm_tokens_total",
    "Tokens consumidos no OpenRouter.",
    ["feature", "model", "kind"],
    registry=REGISTRY,
)

llm_cost_usd_total = Counter(
    "rito_llm_cost_usd_total",
    "Custo acumulado das chamadas de LLM, em dólares.",
    ["feature", "model"],
    registry=REGISTRY,
)

webhook_deliveries_total = Counter(
    "rito_webhook_deliveries_total",
    "Entregas de webhook por desfecho.",
    ["status"],
    registry=REGISTRY,
)

sync_runs_total = Counter(
    "rito_sync_runs_total",
    "Execuções de sincronização externa por desfecho.",
    ["integration", "status"],
    registry=REGISTRY,
)


def record_http_request(*, method: str, route: str, status: int, duration_s: float) -> None:
    http_requests_total.labels(method=method, route=route, status=str(status)).inc()
    http_request_duration_seconds.labels(method=method, route=route).observe(duration_s)
    http_queries_per_request.labels(route=route).observe(current_query_count())


def record_llm_usage(
    *, feature: str, model: str, prompt_tokens: int, completion_tokens: int, cost_usd: float
) -> None:
    llm_tokens_total.labels(feature=feature, model=model, kind="prompt").inc(prompt_tokens)
    llm_tokens_total.labels(feature=feature, model=model, kind="completion").inc(completion_tokens)
    if cost_usd:
        llm_cost_usd_total.labels(feature=feature, model=model).inc(cost_usd)


def record_webhook_delivery(*, status: str) -> None:
    webhook_deliveries_total.labels(status=status).inc()


def record_sync_run(*, integration: str, status: str) -> None:
    sync_runs_total.labels(integration=integration, status=status).inc()


async def observe_queue_depths(redis: "Redis", queues: Sequence[str] = ("celery",)) -> None:
    """Lê o tamanho das filas do broker na hora do scrape.

    Gauge de fila não pode ser incrementado por quem enfileira: o worker consome em
    outro processo e o valor derivaria para sempre. O jeito certo é perguntar ao
    broker no momento da leitura — e é por isso que esta função é chamada pela rota
    `/metrics`, não pelo caminho quente (regra 12).
    """
    for queue in queues:
        try:
            depth = await redis.llen(queue)
        except Exception:
            # Spec 115: a profundidade de UMA fila que não responde não pode derrubar o
            # `/metrics` inteiro — mas engolir em silêncio esconde um Redis quebrado
            # justamente da página que existe para mostrar que algo quebrou.
            logger.warning("profundidade da fila %s indisponível", queue, exc_info=True)
            continue
        celery_queue_depth.labels(queue=queue).set(depth)


def render() -> bytes:
    return generate_latest(REGISTRY)


def instrument_engine(engine: "AsyncEngine") -> None:
    """Conta as queries da requisição corrente.

    Um listener síncrono no engine (o `sync_engine` por baixo do async) é o único ponto
    onde TODA query passa — contar no repositório deixaria de fora o que o SQLAlchemy
    emite sozinho (lazy load, flush, `SELECT` de refresh), que é justamente o que a 098
    precisa enxergar.
    """

    # Assinatura fixada pelo evento do SQLAlchemy, que não publica stubs tipados: os
    # seis parâmetros vêm dele, nesta ordem, e anotá-los seria inventar um contrato.
    def _count(conn, cursor, statement, parameters, context, executemany) -> None:  # type: ignore[no-untyped-def]
        count_query()

    if not event.contains(engine.sync_engine, "before_cursor_execute", _count):
        event.listen(engine.sync_engine, "before_cursor_execute", _count)
