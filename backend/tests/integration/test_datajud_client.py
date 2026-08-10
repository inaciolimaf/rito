"""Client do DataJud contra MockTransport com a fixture real (spec 046, §8)."""

import json
from pathlib import Path

import httpx
import pytest

from app.integrations.datajud.client import (
    DatajudApiError,
    DatajudClient,
    DatajudConfigError,
    DatajudUnauthorizedError,
)
from app.integrations.http.client import ResilientHttpClient

FIXTURES = (
    Path(__file__).resolve().parents[1] / "fixtures" / "http" / "api-publica.datajud.cnj.jus.br"
)
BASE_URL = "https://api-publica.datajud.cnj.jus.br"
API_KEY = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="


def make_client(handler: httpx.MockTransport) -> DatajudClient:
    http = ResilientHttpClient(transport=handler)
    return DatajudClient(http=http, base_url=BASE_URL, api_key=API_KEY)


def fixture_response(name: str, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, content=(FIXTURES / name).read_bytes())


async def test_client_envia_o_header_apikey() -> None:
    """Regra do §5: `Authorization: APIKey <chave>` em toda chamada."""
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization")
        seen["content_type"] = request.headers.get("content-type")
        return fixture_response("tjsp_processo.json")

    client = make_client(httpx.MockTransport(handler))
    await client.search_by_process_number(
        alias="api_publica_tjsp", process_number="00001333920258260334"
    )

    assert seen["authorization"] == f"APIKey {API_KEY}"
    assert seen["content_type"] == "application/json"


async def test_sem_chave_erro_explicito_antes_de_qualquer_chamada() -> None:
    with pytest.raises(DatajudConfigError, match="DATAJUD_API_KEY"):
        DatajudClient(
            http=ResilientHttpClient(transport=httpx.MockTransport(lambda r: httpx.Response(200))),
            base_url=BASE_URL,
            api_key="  ",
        )


async def test_resposta_sem_hits() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return fixture_response("sem_hits.json")

    client = make_client(httpx.MockTransport(handler))
    results = await client.search_by_process_number(
        alias="api_publica_tjsp", process_number="99999999999999999999"
    )

    assert results == []


async def test_numero_de_processo_vai_so_com_digitos() -> None:
    """Regra 5: máscara é removida antes de montar a query."""
    seen_body = b""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_body
        seen_body = request.content
        return fixture_response("sem_hits.json")

    client = make_client(httpx.MockTransport(handler))
    await client.search_by_process_number(
        alias="api_publica_tjsp", process_number="0000133-39.2025.8.26.0334"
    )

    query = json.loads(seen_body)
    assert query["query"]["match"]["numeroProcesso"] == "00001333920258260334"


async def test_401_levanta_erro_especifico() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return fixture_response("401_chave_invalida.json", status_code=401)

    client = make_client(httpx.MockTransport(handler))
    with pytest.raises(DatajudUnauthorizedError):
        await client.search_by_process_number(
            alias="api_publica_tjsp", process_number="00001333920258260334"
        )


async def test_401_nao_entra_em_loop_de_retry() -> None:
    """Regra 3: 401 fica FORA de `HostPolicy.retry_on` (só 429/5xx) — a camada 041
    nunca retenta, então uma única chamada HTTP é feita."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return fixture_response("401_chave_invalida.json", status_code=401)

    client = make_client(httpx.MockTransport(handler))
    with pytest.raises(DatajudUnauthorizedError):
        await client.search_by_process_number(
            alias="api_publica_tjsp", process_number="00001333920258260334"
        )

    assert calls == 1


async def test_resposta_nao_200_nem_401_levanta_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, content=b"Forbidden")

    client = make_client(httpx.MockTransport(handler))
    with pytest.raises(DatajudApiError) as exc_info:
        await client.search_by_process_number(
            alias="api_publica_tjsp", process_number="00001333920258260334"
        )
    assert exc_info.value.status_code == 403
