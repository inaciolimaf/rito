"""Client do DJEN contra MockTransport com as fixtures reais (spec 042, §8)."""

import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from app.integrations.djen.client import (
    DjenApiError,
    DjenClient,
    DjenConfigError,
)
from app.integrations.http.client import ResilientHttpClient

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "http" / "comunicaapi.pje.jus.br"
UA = "Mozilla/5.0 (X11; Linux x86_64) Chrome/150.0.0.0 Safari/537.36"
BASE_URL = "https://comunicaapi.pje.jus.br/api/v1"


def make_djen_client(
    handler: httpx.MockTransport | None = None, user_agent: str = UA
) -> DjenClient:
    assert handler is not None
    http = ResilientHttpClient(transport=handler)
    return DjenClient(http=http, base_url=BASE_URL, user_agent=user_agent)


def fixture_handler(name: str) -> httpx.MockTransport:
    body = (FIXTURES / name).read_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    return httpx.MockTransport(handler)


async def test_client_envia_user_agent_e_query_params() -> None:
    """Regra 1: o User-Agent de browser vai em TODA chamada — sem ele a API dá 403."""
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["user_agent"] = request.headers.get("user-agent")
        seen["query"] = request.url.query.decode()
        return httpx.Response(200, content=(FIXTURES / "tjsp.json").read_bytes())

    client = make_djen_client(httpx.MockTransport(handler))
    page = await client.fetch_communications(
        availability_start=date(2026, 8, 7),
        availability_end=date(2026, 8, 8),
        oab_number="114962",
        oab_state="MG",
        page=2,
        per_page=50,
    )

    assert seen["user_agent"] == UA
    query = seen["query"] or ""
    for expected in (
        "dataDisponibilizacaoInicio=2026-08-07",
        "dataDisponibilizacaoFim=2026-08-08",
        "meio=D",
        "numeroOab=114962",
        "ufOab=MG",
        "pagina=2",
        "itensPorPagina=50",
    ):
        assert expected in query
    assert page.count == json.loads((FIXTURES / "tjsp.json").read_text())["count"]
    assert len(page.items) > 0
    assert page.items[0].court_code == "TJSP"


async def test_sem_user_agent_erro_explicito_antes_de_qualquer_chamada() -> None:
    with pytest.raises(DjenConfigError, match="User-Agent"):
        DjenClient(
            http=ResilientHttpClient(transport=httpx.MockTransport(lambda r: httpx.Response(200))),
            base_url=BASE_URL,
            user_agent="  ",
        )


async def test_itens_por_pagina_acima_de_100_e_limitado() -> None:
    """Regra 9: itensPorPagina nunca passa de 100, para proteger o rate limit."""
    seen_query = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_query
        seen_query = request.url.query.decode()
        return httpx.Response(200, json={"status": "success", "count": 0, "items": []})

    client = make_djen_client(httpx.MockTransport(handler))
    await client.fetch_communications(
        availability_start=date(2026, 8, 7), availability_end=date(2026, 8, 8), per_page=500
    )

    assert "itensPorPagina=100" in seen_query


async def test_resposta_nao_200_levanta_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, content=b"Forbidden")

    client = make_djen_client(httpx.MockTransport(handler))
    with pytest.raises(DjenApiError) as exc_info:
        await client.fetch_communications(
            availability_start=date(2026, 8, 7), availability_end=date(2026, 8, 8)
        )
    assert exc_info.value.status_code == 403


async def test_text_query_envia_parametro_texto() -> None:
    """Spec 044: termos CPF/CNPJ consultam pelo `texto` (full-text no corpo) —
    o DJEN não tem filtro por documento (descoberta verificada ao vivo)."""
    seen_query = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_query
        seen_query = request.url.query.decode()
        return httpx.Response(200, json={"status": "success", "count": 0, "items": []})

    client = make_djen_client(httpx.MockTransport(handler))
    await client.fetch_communications(
        availability_start=date(2026, 8, 7),
        availability_end=date(2026, 8, 8),
        text_query="52998224725",
    )

    assert "texto=52998224725" in seen_query
    assert "numeroOab" not in seen_query
