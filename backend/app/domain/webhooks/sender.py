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

    async def send(
        self, *, url: str, body: bytes, headers: dict[str, str], allow_local: bool
    ) -> SendResult:
        comeco = time.perf_counter()
        destino = url
        try:
            # `follow_redirects=False` de propósito: o redirect é seguido à mão, para
            # que cada salto seja validado.
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False) as client:
                for _salto in range(MAX_REDIRECTS + 1):
                    response = await client.post(destino, content=body, headers=headers)
                    if response.status_code not in (301, 302, 303, 307, 308):
                        return SendResult(
                            status_code=response.status_code,
                            body=response.text,
                            duration_ms=_elapsed(comeco),
                        )
                    localizacao = response.headers.get("location")
                    if not localizacao:
                        return SendResult(
                            status_code=response.status_code,
                            body=response.text,
                            duration_ms=_elapsed(comeco),
                        )
                    destino = validate_webhook_url(
                        urljoin(destino, localizacao), allow_local=allow_local
                    )
            return SendResult(
                status_code=None,
                body="",
                duration_ms=_elapsed(comeco),
                error="Redirecionamentos demais.",
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
