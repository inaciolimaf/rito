from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import (
    handle_http_exception,
    handle_unhandled_exception,
    handle_validation_error,
)


class _EchoPayload(BaseModel):
    name: str


def _build_test_app() -> FastAPI:
    test_app = FastAPI()
    test_app.add_exception_handler(RequestValidationError, handle_validation_error)
    test_app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    test_app.add_exception_handler(Exception, handle_unhandled_exception)

    @test_app.post("/echo")
    async def echo(payload: _EchoPayload) -> _EchoPayload:
        return payload

    @test_app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("erro interno de teste")

    return test_app


async def test_validation_error_returns_problem_json() -> None:
    transport = ASGITransport(app=_build_test_app())
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/echo", json={})

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["type"] == "https://rito.app/errors/validation"
    assert body["status"] == 422
    assert body["errors"]


async def test_unhandled_exception_returns_generic_500_without_stack_trace() -> None:
    transport = ASGITransport(app=_build_test_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/boom")

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["detail"] == "Erro interno do servidor."
    assert "RuntimeError" not in response.text
    assert "Traceback" not in response.text
