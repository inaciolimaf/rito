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
from typing import Any

from opentelemetry.trace import SpanKind, Status, StatusCode
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


class ObservabilityMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        request_id = request.headers.get(REQUEST_ID_HEADER) or new_request_id()
        tokens = (
            request_id_var.set(request_id),
            route_var.set(request.url.path),
            start_query_counter(),
            tenant_id_var.set(None),
            user_id_var.set(None),
        )
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
                rota = route_template(scope) or request.url.path
                span.update_name(f"{request.method} {rota}")
                span.set_attribute("http.route", rota)
                span.set_attribute("http.response.status_code", status_code)
                if status_code >= 500:
                    # Regra 11: erro é sempre exportado, sorteado ou não. Quem lê isso é
                    # o processor no `on_end` — daí o status precisar estar posto aqui.
                    span.set_status(Status(StatusCode.ERROR))
        finally:
            duracao_s = time.perf_counter() - started
            template = route_template(scope)
            rota = template or request.url.path
            route_var.set(rota)
            metrics.record_http_request(
                method=request.method,
                # Requisição que não casou rota nenhuma (404, varredura de robô) entra na
                # métrica sob um rótulo só. Rotular pelo caminho pedido deixaria a
                # cardinalidade da série nas mãos de quem faz a requisição.
                route=template or UNMATCHED_ROUTE,
                status=status_code,
                duration_s=duracao_s,
            )
            # Regra 9: a linha de requisição não carrega stack — nem quando deu 500. O
            # stack já saiu no log de erro do handler, com a exceção inteira; repeti-lo
            # aqui dobraria o volume sem acrescentar informação.
            logger.info(
                "requisição concluída",
                extra={
                    "method": request.method,
                    "route": rota,
                    "status": status_code,
                    "duration_ms": int(duracao_s * 1000),
                    "query_count": current_query_count(),
                },
            )
            request_id_var.reset(tokens[0])
            route_var.reset(tokens[1])
            query_counter_var.reset(tokens[2])
            tenant_id_var.reset(tokens[3])
            user_id_var.reset(tokens[4])
