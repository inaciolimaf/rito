"""Middleware da API pública (spec 095, regras 5 e 9).

Duas coisas que precisam acontecer em TODA resposta e que não cabem numa dependência:
os headers de limite (que a spec exige mesmo nas respostas bem-sucedidas) e o registro
da requisição — inclusive quando ela terminou em erro, que é o caso que mais interessa.

`last_used_at` é atualizado aqui e não na autenticação (regra 13): um UPDATE por
requisição no caminho crítico transformaria toda chamada numa escrita.
"""

import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.public.deps import record_request

PUBLIC_PREFIX = "/api/public/"


class PublicApiMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if not request.url.path.startswith(PUBLIC_PREFIX):
            return await call_next(request)

        comeco = time.perf_counter()
        response = await call_next(request)
        duracao = int((time.perf_counter() - comeco) * 1000)

        limite = getattr(request.state, "rate_limit", None)
        if limite is not None and "X-RateLimit-Limit" not in response.headers:
            total, restante, reset = limite
            response.headers["X-RateLimit-Limit"] = str(total)
            response.headers["X-RateLimit-Remaining"] = str(restante)
            response.headers["X-RateLimit-Reset"] = str(reset)

        await record_request(request, status_code=response.status_code, duration_ms=duracao)
        return response
