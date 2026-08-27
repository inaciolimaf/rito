"""Correlação atravessando a fila (spec 097, regras 2 e 5).

O ponto da regra 2 é seguir uma ação **do clique até o worker**. Uma intimação que vira
tarefa passa por request HTTP, task de sincronização e task de criação; se cada trecho
tiver um id próprio, o log de cada um está correto e o conjunto é inútil.

As duas funções abaixo são o contrato, e são puras de propósito: nada de Celery aqui
dentro. Quem enfileira chama `build_task_headers()` e manda o dicionário junto; quem
executa chama `bind_task_headers()` e devolve o que recebeu no fim. Os sinais do Celery
(`app/workers/observability.py`) são só a cola — e é essa separação que permite testar a
propagação sem broker, sem worker e sem rede (CLAUDE.md §3).
"""

from collections.abc import Mapping
from contextvars import Token
from dataclasses import dataclass

from opentelemetry import trace
from opentelemetry.context import Context, attach, detach
from opentelemetry.trace import SpanKind

from app.core.observability.context import (
    CorrelationSnapshot,
    bind_correlation,
    current_correlation,
    reset_correlation,
)
from app.core.observability.tracing import extract_context, get_tracer, inject_context

REQUEST_ID_HEADER = "rito-request-id"
TENANT_ID_HEADER = "rito-tenant-id"
USER_ID_HEADER = "rito-user-id"


def build_task_headers() -> dict[str, str]:
    """Fotografa o contexto de quem está enfileirando, para viajar com a mensagem."""
    snapshot = current_correlation()
    carrier: dict[str, str] = {}
    if snapshot.request_id:
        carrier[REQUEST_ID_HEADER] = snapshot.request_id
    if snapshot.tenant_id:
        carrier[TENANT_ID_HEADER] = snapshot.tenant_id
    if snapshot.user_id:
        carrier[USER_ID_HEADER] = snapshot.user_id
    # `traceparent` no formato W3C — o mesmo que qualquer outro sistema entende.
    inject_context(carrier)
    return carrier


@dataclass
class TaskScope:
    """O que precisa ser desfeito quando a task termina."""

    correlation_tokens: list[Token[str | None]]
    otel_token: object
    span: trace.Span


def bind_task_headers(headers: Mapping[str, str], *, task_name: str) -> TaskScope:
    """Reconstrói contexto e trace do lado do worker e abre o span da task.

    Sem `traceparent` no carrier — task disparada pelo beat, não por uma requisição — o
    span nasce raiz. Isso é correto: não existe request para continuar.
    """
    parent: Context = extract_context(headers)
    otel_token = attach(parent)
    span = get_tracer().start_span(
        f"celery {task_name}",
        context=parent,
        kind=SpanKind.CONSUMER,
        attributes={"messaging.system": "celery", "messaging.destination": task_name},
    )
    tokens = bind_correlation(
        CorrelationSnapshot(
            request_id=headers.get(REQUEST_ID_HEADER),
            tenant_id=headers.get(TENANT_ID_HEADER),
            user_id=headers.get(USER_ID_HEADER),
        )
    )
    return TaskScope(correlation_tokens=tokens, otel_token=otel_token, span=span)


def release_task_scope(scope: TaskScope, *, error: BaseException | None = None) -> None:
    if error is not None:
        scope.span.record_exception(error)
        scope.span.set_status(trace.Status(trace.StatusCode.ERROR, str(error)))
    scope.span.end()
    detach(scope.otel_token)  # type: ignore[arg-type]  # detach recebe o token opaco que attach devolveu
    reset_correlation(scope.correlation_tokens)
