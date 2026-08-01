import logging
from collections.abc import Sequence
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
    errors: Sequence[Any] | None = None,
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
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(body),
        media_type=PROBLEM_CONTENT_TYPE,
    )


async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return _problem_response(
        status_code=422,
        detail="Um ou mais campos são inválidos.",
        instance=request.url.path,
        errors=exc.errors(),
    )


async def handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    detail: Any = exc.detail
    errors: Sequence[Any] | None = None
    # Convenção para validação de negócio (não de schema): raise HTTPException(
    # detail={"detail": "...", "errors": [...]}) quando 1 mensagem não basta
    # (ex.: política de senha listando cada critério que falhou).
    if isinstance(detail, dict) and "errors" in detail:
        errors = detail.get("errors")
        detail = detail.get("detail", "Erro de validação.")
    return _problem_response(
        status_code=exc.status_code,
        detail=str(detail),
        instance=request.url.path,
        errors=errors,
    )


async def handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Erro não tratado", exc_info=exc)
    return _problem_response(
        status_code=500,
        detail="Erro interno do servidor.",
        instance=request.url.path,
    )
