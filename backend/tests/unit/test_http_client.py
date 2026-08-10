"""Testes de unidade do client HTTP resiliente (spec 041, §8).

Nenhum teste dorme nem toca a rede: o sleep, o jitter e o relógio são injetados
no client e o transporte é o MockTransport do httpx.
"""

import base64
import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from app.integrations.http.breaker import CircuitState
from app.integrations.http.cache import CachedEntry
from app.integrations.http.client import MAX_BODY_BYTES, ResilientHttpClient
from app.integrations.http.fixtures import FixtureTransport, fixture_key
from app.integrations.http.types import (
    CircuitOpenError,
    FixtureMissingError,
    HostPolicy,
    HttpRequestError,
    HttpStatusError,
    ResponseTooLargeError,
)

URL = "http://api-falsa.test/coisas"


class InMemoryCache:
    """CacheStore em memória — mesmo contrato do ConditionalCache, sem Redis."""

    def __init__(self) -> None:
        self.entries: dict[str, CachedEntry] = {}

    async def get(self, key: str) -> CachedEntry | None:
        return self.entries.get(key)

    async def store(
        self,
        key: str,
        *,
        etag: str | None,
        last_modified: str | None,
        headers: dict[str, str],
        body: bytes,
    ) -> None:
        self.entries[key] = CachedEntry(
            etag=etag, last_modified=last_modified, headers=headers, body=body
        )


async def _no_sleep(seconds: float) -> None:
    pass


def make_client(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    policy: HostPolicy | None = None,
    sleeps: list[float] | None = None,
    clock: Callable[[], float] | None = None,
    cache: InMemoryCache | None = None,
) -> ResilientHttpClient:
    async def fake_sleep(seconds: float) -> None:
        assert sleeps is not None
        sleeps.append(seconds)

    return ResilientHttpClient(
        transport=httpx.MockTransport(handler),
        default_policy=policy or HostPolicy(),
        sleep=fake_sleep if sleeps is not None else _no_sleep,
        jitter=lambda: 1.0,  # jitter fixo: backoff determinístico no teste
        clock=clock or (lambda: 0.0),
        cache=cache,
    )


def respond(
    status: int, body: bytes = b"ok", headers: dict[str, str] | None = None
) -> httpx.Response:
    return httpx.Response(status, content=body, headers=headers or {})


@pytest.mark.parametrize("status", [500, 502, 503, 504])
async def test_retenta_status_transitorio(status: int) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return respond(status) if len(calls) < 3 else respond(200)

    client = make_client(handler, sleeps=[])
    response = await client.request("GET", URL)

    assert response.status_code == 200
    assert len(calls) == 3
    await client.aclose()


async def test_retenta_timeout() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise httpx.ConnectTimeout("estourou", request=request)
        return respond(200)

    client = make_client(handler, sleeps=[])
    response = await client.request("GET", URL)

    assert response.status_code == 200
    assert calls == 3
    await client.aclose()


@pytest.mark.parametrize("status", [400, 404])
async def test_status_4xx_nao_e_retentado(status: int) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return respond(status)

    client = make_client(handler, sleeps=[])
    response = await client.request("GET", URL)

    assert response.status_code == status
    assert calls == 1
    await client.aclose()


async def test_erro_de_transporte_esgotado_levanta_http_request_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("caiu", request=request)

    client = make_client(handler, policy=HostPolicy(max_retries=2), sleeps=[])
    with pytest.raises(HttpRequestError):
        await client.request("GET", URL)
    await client.aclose()


async def test_backoff_cresce_e_respeita_o_teto() -> None:
    sleeps: list[float] = []

    client = make_client(
        lambda request: respond(500),
        policy=HostPolicy(max_retries=7, backoff_base_s=1.0, backoff_cap_s=30.0),
        sleeps=sleeps,
    )
    with pytest.raises(HttpStatusError):
        await client.request("GET", URL)

    # base=1, jitter=1: 1, 2, 4, 8, 16, e a partir daí o teto de 30 manda.
    assert sleeps == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0]
    await client.aclose()


async def test_retry_after_prevalece_sobre_o_backoff() -> None:
    sleeps: list[float] = []
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return respond(429, headers={"Retry-After": "7"})
        return respond(200)

    client = make_client(handler, sleeps=sleeps)
    response = await client.request("GET", URL)

    assert response.status_code == 200
    assert sleeps == [7.0]
    await client.aclose()


async def test_breaker_abre_apos_n_falhas_e_nao_toca_a_rede() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return respond(500)

    client = make_client(
        handler,
        policy=HostPolicy(max_retries=0, breaker_failure_threshold=3),
        sleeps=[],
    )
    for _ in range(3):
        with pytest.raises(HttpStatusError):
            await client.request("GET", URL)
    assert calls == 3

    # Circuito aberto: falha imediata, sem chamada de rede.
    with pytest.raises(CircuitOpenError):
        await client.request("GET", URL)
    assert calls == 3
    await client.aclose()


async def test_breaker_meio_aberto_libera_uma_e_fecha_no_sucesso() -> None:
    now = [0.0]
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return respond(500) if calls == 1 else respond(200)

    client = make_client(
        handler,
        policy=HostPolicy(max_retries=0, breaker_failure_threshold=1, breaker_reset_after_s=60),
        sleeps=[],
        clock=lambda: now[0],
    )
    with pytest.raises(HttpStatusError):
        await client.request("GET", URL)

    # Ainda dentro da janela de reset: continua aberto.
    now[0] = 59.0
    with pytest.raises(CircuitOpenError):
        await client.request("GET", URL)

    # Passou o reset: meio-aberto libera a prova, que fecha o circuito no sucesso.
    now[0] = 61.0
    response = await client.request("GET", URL)
    assert response.status_code == 200
    assert client.breaker_state("api-falsa.test") is CircuitState.CLOSED

    response = await client.request("GET", URL)
    assert response.status_code == 200
    assert calls == 3
    await client.aclose()


async def test_corpo_acima_do_limite_e_rejeitado_pelo_content_length() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return respond(200, body=b"pequeno", headers={"Content-Length": str(MAX_BODY_BYTES + 1)})

    client = make_client(handler, sleeps=[])
    with pytest.raises(ResponseTooLargeError):
        await client.request("GET", URL)
    await client.aclose()


async def test_corpo_acima_do_limite_e_rejeitado_depois_de_ler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return respond(200, body=b"x" * 200)

    # Sem Content-Length desonesto, o limite é conferido no corpo já lido —
    # o monkeypatch encolhe o limite para o teste não alocar 10 MB à toa.
    monkeypatch.setattr("app.integrations.http.client.MAX_BODY_BYTES", 100)
    client = make_client(handler, sleeps=[])
    with pytest.raises(ResponseTooLargeError):
        await client.request("GET", URL)
    await client.aclose()


async def test_cache_condicional_revalida_e_reusa_corpo_no_304() -> None:
    seen_if_none_match: list[str | None] = []
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        seen_if_none_match.append(request.headers.get("if-none-match"))
        if calls == 1:
            return respond(200, body=b"conteudo-v1", headers={"ETag": '"abc123"'})
        return respond(304)

    client = make_client(handler, sleeps=[], cache=InMemoryCache())

    first = await client.request("GET", URL)
    assert first.status_code == 200
    assert first.content == b"conteudo-v1"

    second = await client.request("GET", URL)
    assert seen_if_none_match == [None, '"abc123"']
    assert second.status_code == 200
    assert second.content == b"conteudo-v1"
    await client.aclose()


# --- fixtures (replay/gravação) ---


def _write_fixture(root: Path, host: str, method: str, url: str, body: bytes = b"") -> None:
    path = root / host / f"{fixture_key(method, url, body)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "method": method,
                "url": url,
                "status_code": 200,
                "headers": {"Content-Type": "application/json"},
                "body_b64": base64.b64encode(b'{"ok": true}').decode(),
            }
        ),
        encoding="utf-8",
    )


async def test_fixture_replay_devolve_resposta_gravada(tmp_path: Path) -> None:
    url = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"
    _write_fixture(tmp_path, "comunicaapi.pje.jus.br", "GET", url)

    client = ResilientHttpClient(transport=FixtureTransport(tmp_path), sleep=_no_sleep)
    response = await client.request("GET", url)

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    await client.aclose()


async def test_fixture_ausente_falha_explicitamente_sem_cair_na_rede(tmp_path: Path) -> None:
    """Guarda central da regra 7: replay sem fixture NUNCA tenta a rede."""
    client = ResilientHttpClient(transport=FixtureTransport(tmp_path), sleep=_no_sleep)
    with pytest.raises(FixtureMissingError, match="fixture ausente"):
        await client.request("GET", "https://api-publica.datajud.cnj.jus.br/api_publica_tjdf")
    await client.aclose()


async def test_gravacao_redige_headers_sensiveis(tmp_path: Path) -> None:
    transport = FixtureTransport(tmp_path, record=True)
    request = httpx.Request("GET", "https://exemplo.test/dados")
    response = httpx.Response(
        200,
        content=b"{}",
        headers={
            "Authorization": "Bearer segredo",
            "Set-Cookie": "sessao=abc",
            "X-Api-Key": "chave",
            "Content-Type": "application/json",
        },
        request=request,
    )
    path = (
        tmp_path / "exemplo.test" / f"{fixture_key('GET', 'https://exemplo.test/dados', b'')}.json"
    )
    transport.write_fixture(path, request, response, b"{}")

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["headers"]["content-type"] == "application/json"
    for sensivel in ("authorization", "set-cookie", "x-api-key"):
        assert sensivel not in data["headers"]
    await transport.aclose()
