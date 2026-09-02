"""Middleware de observabilidade (spec 097, regras 1, 2, 4, 6 e 9).

Uma passagem por requisição faz cinco coisas que precisam acontecer para TODA rota e que
nenhuma dependência conseguiria garantir (dependência não roda quando o 404 nem chega ao
endpoint, nem quando a rota levanta antes de resolver `Depends`):

1. resolve o `request_id` (header do cliente ou novo) e o publica no contexto;
2. abre o contador de queries da requisição;
3. abre o span raiz do trace;
4. mede a duração, conta a métrica e emite **uma** linha de log por requisição;
5. devolve o `X-Request-Id` — é o número de protocolo que o usuário passa ao suporte.

## Por que ASGI puro e não `BaseHTTPMiddleware`

`BaseHTTPMiddleware.call_next` executa o resto da aplicação numa **task separada**. Task
nova recebe uma cópia do contexto, e o que a rota escreve lá dentro não volta: o
`tenant_id` que `get_current_user` publica e o contador de queries chegariam sempre
vazios aqui. Middleware ASGI puro chama a aplicação com um `await` comum, na mesma task,
e o contexto é o mesmo dos dois lados — que é a premissa inteira da regra 1.
"""

import logging
import time
from contextvars import Token
from typing import Any

from opentelemetry.trace import Span, SpanKind, Status, StatusCode
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.observability import metrics
from app.core.observability.context import (
    current_query_count,
    new_request_id,
    query_counter_var,
    request_id_var,
    route_var,
    start_query_counter,
    tenant_id_var,
    user_id_var,
)
from app.core.observability.tracing import get_tracer

logger = logging.getLogger("rito.request")

REQUEST_ID_HEADER = "X-Request-Id"
UNMATCHED_ROUTE = "<unmatched>"


def route_template(scope: Scope) -> str | None:
    """Template da rota casada (`/api/v1/users/{user_id}`), ou `None` se nada casou.

    Não dá para usar `route.path_format` direto: o FastAPI monta os routers incluídos
    como sub-aplicações, e o `path_format` que chega no scope é o do router — sem o
    prefixo `/api/v1`. Reconstruir a partir do caminho concreto e dos `path_params`
    resolve isso sem depender do formato interno do FastAPI, que já mudou uma vez.

    Parâmetro do tipo `:path` (que atravessa barras) não é reconstruído — o Rito não tem
    nenhum, e o segmento cru é um fallback correto, só mais específico.
    """
    if scope.get("route") is None:
        return None
    caminho: str = scope.get("path", "")
    params: dict[str, Any] = scope.get("path_params") or {}
    if not params:
        return caminho
    marcadores = {str(valor): f"{{{nome}}}" for nome, valor in params.items()}
    return "/".join(marcadores.get(segmento, segmento) for segmento in caminho.split("/"))


def _record_and_log(request: Request, scope: Scope, status_code: int, *, duration_s: float) -> None:
    """Métrica e linha de log da requisição concluída (spec 121).

    Rodava no `finally` do `__call__`, com 27 linhas dentro de um bloco que já era o mais
    longo do backend — e é trabalho de PÓS-requisição, não de despacho: sai daqui inteiro.
    """
    template = route_template(scope)
    rota = template or request.url.path
    route_var.set(rota)
    metrics.record_http_request(
        method=request.method,
        # Requisição que não casou rota nenhuma (404, varredura de robô) entra na métrica
        # sob um rótulo só. Rotular pelo caminho pedido deixaria a cardinalidade da série
        # nas mãos de quem faz a requisição.
        route=template or UNMATCHED_ROUTE,
        status=status_code,
        duration_s=duration_s,
    )
    # Regra 9: a linha de requisição não carrega stack — nem quando deu 500. O stack já
    # saiu no log de erro do handler, com a exceção inteira; repeti-lo aqui dobraria o
    # volume sem acrescentar informação.
    logger.info(
        "requisição concluída",
        extra={
            "method": request.method,
            "route": rota,
            "status": status_code,
            "duration_ms": int(duration_s * 1000),
            "query_count": current_query_count(),
        },
    )


def _enter_context(request: Request, request_id: str) -> tuple[Token[Any], ...]:
    """Abre o contexto da requisição e devolve os tokens na ordem de criação.

    `route_var` recebe o caminho cru — o template (`/lawsuits/{id}`) só é conhecido depois
    que o roteador casou, e é `_close_span` quem o corrige no span. O log estruturado usa
    o caminho cru de propósito: se a requisição morrer antes do roteamento, é o único que
    existe.
    """
    return (
        request_id_var.set(request_id),
        route_var.set(request.url.path),
        start_query_counter(),
        tenant_id_var.set(None),
        user_id_var.set(None),
    )


def _close_span(span: Span, request: Request, scope: Scope, status_code: int) -> None:
    """Nomeia o span pela rota casada e marca erro de servidor.

    O nome só pode ser posto aqui: `start_as_current_span` roda antes do roteamento e não
    conhece o template, e span nomeado pelo caminho cru gera uma série por UUID.
    """
    rota = route_template(scope) or request.url.path
    span.update_name(f"{request.method} {rota}")
    span.set_attribute("http.route", rota)
    span.set_attribute("http.response.status_code", status_code)
    if status_code >= 500:
        # Regra 11: erro é sempre exportado, sorteado ou não. Quem lê isso é o processor
        # no `on_end` — daí o status precisar estar posto aqui.
        span.set_status(Status(StatusCode.ERROR))


def _reset_context(tokens: tuple[Token[Any], ...]) -> None:
    """Devolve as cinco variáveis de contexto ao valor de antes desta requisição.

    A ordem espelha a de `tokens`, montada na entrada. Resetar é obrigatório mesmo quando
    a requisição estourou: sem isso o `request_id` da requisição morta vazaria para a
    próxima que reusar a mesma task do event loop.
    """
    request_id_var.reset(tokens[0])
    route_var.reset(tokens[1])
    query_counter_var.reset(tokens[2])
    tenant_id_var.reset(tokens[3])
    user_id_var.reset(tokens[4])


class ObservabilityMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        request_id = request.headers.get(REQUEST_ID_HEADER) or new_request_id()
        tokens = _enter_context(request, request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_com_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            with get_tracer().start_as_current_span(
                f"{request.method} {request.url.path}",
                kind=SpanKind.SERVER,
                attributes={
                    "http.request.method": request.method,
                    "url.path": request.url.path,
                    "rito.request_id": request_id,
                },
            ) as span:
                await self.app(scope, receive, send_com_request_id)
                _close_span(span, request, scope, status_code)
        finally:
            _record_and_log(request, scope, status_code, duration_s=time.perf_counter() - started)
            _reset_context(tokens)
