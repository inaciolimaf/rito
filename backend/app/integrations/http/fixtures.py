"""Transporte de fixtures: replay em teste, gravação sob HTTP_RECORD=1 (spec 041, §2).

Regra 7: em modo replay, uma fixture ausente FALHA explicitamente — o transporte
nunca deixa a chamada cair na rede. Regra 8: em modo gravação, a resposta real é
persistida com redação de headers sensíveis.

O nome do arquivo é o sha256 de `método + url + corpo`, então a mesma chamada
sempre resolve para a mesma fixture, e chamadas distintas não colidem.
"""

import base64
import hashlib
import json
from pathlib import Path

import httpx

from app.integrations.http.types import FixtureMissingError

# Headers que nunca vão para uma fixture gravada (regra 8) — a fixture é commitada
# no repositório, então credencial nela seria vazamento.
_SENSITIVE_HEADERS = frozenset(
    {"authorization", "proxy-authorization", "cookie", "set-cookie", "x-api-key", "apikey"}
)


def fixture_key(method: str, url: str, body: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(method.upper().encode())
    digest.update(b" ")
    digest.update(url.encode())
    digest.update(b" ")
    digest.update(body)
    return digest.hexdigest()


class FixtureTransport(httpx.AsyncBaseTransport):
    """Transporte httpx que lê/grava fixtures em `<root>/<host>/<sha256>.json`."""

    def __init__(self, root: Path, *, record: bool = False) -> None:
        self._root = root
        self._record = record
        self._real = httpx.AsyncHTTPTransport() if record else None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = request.content
        host = request.url.host or "unknown"
        path = self._root / host / f"{fixture_key(request.method, str(request.url), body)}.json"

        if self._record:
            assert self._real is not None
            response = await self._real.handle_async_request(request)
            content = await response.aread()
            self.write_fixture(path, request, response, content)
            return httpx.Response(
                status_code=response.status_code,
                headers=dict(response.headers),
                content=content,
                request=request,
            )

        if not path.exists():
            raise FixtureMissingError(str(path))

        data = json.loads(path.read_text(encoding="utf-8"))
        return httpx.Response(
            status_code=data["status_code"],
            headers=data["headers"],
            content=base64.b64decode(data["body_b64"]),
            request=request,
        )

    def write_fixture(
        self, path: Path, request: httpx.Request, response: httpx.Response, content: bytes
    ) -> None:
        headers = {k: v for k, v in response.headers.items() if k.lower() not in _SENSITIVE_HEADERS}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "method": request.method,
                    "url": str(request.url),
                    "status_code": response.status_code,
                    "headers": headers,
                    "body_b64": base64.b64encode(content).decode(),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    async def aclose(self) -> None:
        if self._real is not None:
            await self._real.aclose()
