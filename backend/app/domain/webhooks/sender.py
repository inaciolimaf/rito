"""O transporte do webhook (spec 093).

Interface separada porque é a fronteira com a rede: em teste entra uma implementação que
devolve o que o caso precisa (500, 400, timeout) sem abrir socket nenhum — regra do
CLAUDE.md §3, e a única forma de testar retry sem esperar minutos de backoff.

Redirecionamento é seguido AQUI, no máximo três vezes, com cada `Location` passando pela
mesma peneira de SSRF (regra 7): um destino público pode devolver um `Location` privado, e
seguir redirect cegamente desfaz toda a validação feita na URL original.
"""

import time
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin

import httpx

from app.domain.webhooks.ssrf import UnsafeUrlError, validate_webhook_url

# Regra 4.
TIMEOUT_SECONDS = 10.0
MAX_REDIRECTS = 3


@dataclass(frozen=True)
class SendResult:
    status_code: int | None
    body: str
    duration_ms: int
    error: str | None = None

    @property
    def ok(self) -> bool:
        """Regra 1: 2xx é entrega. O Rito não interpreta o corpo da resposta."""
        return self.status_code is not None and 200 <= self.status_code < 300

    @property
    def retryable(self) -> bool:
        """Regra 3: conexão, timeout e 5xx retentam. 4xx é erro de configuração —
        retentar um 401 três vezes só produz três 401."""
        if self.status_code is None:
            return True
        return self.status_code >= 500


class WebhookSender(Protocol):
    async def send(
        self, *, url: str, body: bytes, headers: dict[str, str], allow_local: bool
    ) -> SendResult: ...


class HttpxWebhookSender:
    """Implementação real, sobre httpx."""

    def __init__(self, *, timeout_s: float = TIMEOUT_SECONDS) -> None:
        self._timeout = timeout_s

    async def _postar_seguindo_redirects(
        self,
        client: httpx.AsyncClient,
        *,
        url: str,
        body: bytes,
        headers: dict[str, str],
        allow_local: bool,
    ) -> httpx.Response | None:
        """Posta e segue redirect À MÃO, validando cada salto contra o SSRF.

        É por isso que `follow_redirects` fica desligado: o httpx seguiria sozinho, e um
        destino que responde 302 para `169.254.169.254` levaria o payload assinado direto
        para o serviço de metadados da nuvem. `None` significa que os saltos acabaram sem
        resposta final.
        """
        destino = url
        for _salto in range(MAX_REDIRECTS + 1):
            response = await client.post(destino, content=body, headers=headers)
            localizacao = response.headers.get("location")
            # Sem `Location`, o 3xx não tem para onde ir — vale como resposta final.
            if response.status_code not in (301, 302, 303, 307, 308) or not localizacao:
                return response
            destino = validate_webhook_url(urljoin(destino, localizacao), allow_local=allow_local)
        return None

    async def send(
        self, *, url: str, body: bytes, headers: dict[str, str], allow_local: bool
    ) -> SendResult:
        comeco = time.perf_counter()
        try:
            # `follow_redirects=False` de propósito: o redirect é seguido à mão, para
            # que cada salto seja validado.
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False) as client:
                resposta = await self._postar_seguindo_redirects(
                    client, url=url, body=body, headers=headers, allow_local=allow_local
                )
            if resposta is None:
                return SendResult(
                    status_code=None,
                    body="",
                    duration_ms=_elapsed(comeco),
                    error="Redirecionamentos demais.",
                )
            return SendResult(
                status_code=resposta.status_code,
                body=resposta.text,
                duration_ms=_elapsed(comeco),
            )
        except UnsafeUrlError as exc:
            return SendResult(
                status_code=None,
                body="",
                duration_ms=_elapsed(comeco),
                error=f"Redirecionamento bloqueado: {exc.detail}",
            )
        except httpx.TimeoutException:
            return SendResult(
                status_code=None,
                body="",
                duration_ms=_elapsed(comeco),
                error=f"Sem resposta em {self._timeout:.0f}s.",
            )
        except httpx.HTTPError as exc:
            return SendResult(
                status_code=None, body="", duration_ms=_elapsed(comeco), error=str(exc)
            )


def _elapsed(comeco: float) -> int:
    return int((time.perf_counter() - comeco) * 1000)
