import logging
from collections.abc import Mapping, Sequence
from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

PROBLEM_CONTENT_TYPE = "application/problem+json"

_SLUGS_BY_STATUS = {
    400: "bad-request",
    401: "unauthorized",
    403: "forbidden",
    404: "not-found",
    409: "conflict",
    422: "validation",
    500: "internal",
}

_TITLES_BY_STATUS = {
    400: "Requisição inválida",
    401: "Não autenticado",
    403: "Acesso negado",
    404: "Recurso não encontrado",
    409: "Conflito",
    422: "Dados inválidos",
    500: "Erro interno",
}


def _problem_response(
    status_code: int,
    detail: str,
    instance: str,
    # Any: cada chamador tem uma forma diferente de erro de campo (RequestValidationError
    # do Pydantic, lista de strings da política de senha) — RFC 7807 não fixa um schema.
    errors: Sequence[Any] | None = None,
    extra: dict[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    slug = _SLUGS_BY_STATUS.get(status_code, "error")
    title = _TITLES_BY_STATUS.get(status_code, "Erro")
    body: dict[str, Any] = {
        "type": f"https://rito.app/errors/{slug}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": instance,
    }
    if errors is not None:
        body["errors"] = errors
    if extra:
        # Membros de extensão do RFC 7807 (ex.: existing_id da duplicata, spec 032).
        body.update(extra)
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(body),
        media_type=PROBLEM_CONTENT_TYPE,
        # Spec 095: `Retry-After` no 429 e `WWW-Authenticate` no 401 são parte do
        # protocolo, não decoração — um cliente HTTP automatizado depende deles, e até
        # aqui o handler os descartava silenciosamente.
        headers=dict(headers) if headers else None,
    )


def _as_type[E: Exception](tipo: type[E], exc: Exception) -> E:
    """`exc` com o tipo que o handler foi registrado para tratar (spec 115).

    O FastAPI tipa todo handler como recebendo `Exception`, mas despacha pelo tipo com que
    ele foi registrado — então o `isinstance` aqui é verdade por construção. Era um
    `assert`, e `assert` some sob `python -O`: aí o `mypy` teria estreitado um tipo que
    nada garante em produção, e um erro de registro viraria `AttributeError` no meio da
    montagem da resposta de erro. Que é o pior momento possível para um erro novo.
    """
    if not isinstance(exc, tipo):  # pragma: no cover - o FastAPI despacha por tipo
        raise TypeError(f"handler de {tipo.__name__} recebeu {type(exc).__name__}")
    return exc


async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    erro = _as_type(RequestValidationError, exc)
    return _problem_response(
        status_code=422,
        detail="Um ou mais campos são inválidos.",
        instance=request.url.path,
        errors=erro.errors(),
    )


async def handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    erro = _as_type(StarletteHTTPException, exc)
    # Any: starlette tipa HTTPException.detail como Any — pode ser str ou um dict de
    # convenção (ver abaixo).
    detail: Any = erro.detail
    errors: Sequence[Any] | None = None
    extra: dict[str, Any] | None = None
    # Convenção para validação de negócio (não de schema): raise HTTPException(
    # detail={"detail": "...", "errors": [...]}) quando 1 mensagem não basta
    # (ex.: política de senha listando cada critério que falhou). Chaves além de
    # "detail"/"errors" viram membros de extensão do problem+json (ex.: existing_id).
    if isinstance(detail, dict):
        errors = detail.get("errors")
        extra = {key: value for key, value in detail.items() if key not in ("detail", "errors")}
        detail = detail.get("detail", "Erro de validação.")
    return _problem_response(
        status_code=erro.status_code,
        detail=str(detail),
        instance=request.url.path,
        errors=errors,
        extra=extra or None,
        headers=erro.headers,
    )


async def handle_budget_exceeded(request: Request, exc: Exception) -> JSONResponse:
    """Spec 090, alvo 2: teto de IA estourado vale para TODA rota de IA.

    É handler global e não `try/except` em cada router porque a política é uma só — oito
    cópias divergiriam, e a nona rota de IA nasceria sem nenhuma. A resposta traz os dois
    números para a UI poder dizer quanto falta em vez de só "não deu".
    """
    from app.domain.ai.budget import BudgetExceededError

    erro = _as_type(BudgetExceededError, exc)
    return _problem_response(
        status_code=409,
        detail=str(exc),
        instance=request.url.path,
        extra={"spent_usd": float(erro.spent), "limit_usd": float(erro.limit)},
    )


async def handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Erro não tratado", exc_info=exc)
    return _problem_response(
        status_code=500,
        detail="Erro interno do servidor.",
        instance=request.url.path,
    )
