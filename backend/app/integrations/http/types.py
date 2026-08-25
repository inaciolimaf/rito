"""Tipos e erros da camada HTTP resiliente (spec 041, §5)."""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol


class HttpClient(Protocol):
    """Interface consumida pelos clients de integração (DJEN, DataJud, OpenRouter).

    OCP (CLAUDE.md §5): nenhum service importa httpx — adicionar uma integração
    nova é implementar o consumo desta interface, e nos testes qualquer fake que
    a implemente é intercambiável com o client real (LSP).
    """

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        content: bytes | None = None,
    ) -> "HttpResponse": ...


class StreamingHttpClient(Protocol):
    """Streaming linha a linha (spec 081, regra 8) — interface separada de propósito
    (ISP): só o client de LLM precisa dela, e nenhum fake de `HttpClient` é obrigado a
    implementar streaming para continuar servindo aos outros consumidores."""

    def stream_lines(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
        timeout_s: float | None = None,
    ) -> "AsyncIterator[str]": ...


@dataclass(frozen=True)
class HostPolicy:
    """Política de resiliência por host. Hosts sem política própria usam o default."""

    timeout_s: float = 30.0
    max_retries: int = 3
    backoff_base_s: float = 0.5
    backoff_cap_s: float = 30.0
    rate_limit_per_minute: int | None = None
    breaker_failure_threshold: int = 5
    breaker_reset_after_s: float = 60.0
    retry_on: tuple[int, ...] = (429, 500, 502, 503, 504)


@dataclass
class HttpResponse:
    """Resposta desacoplada do httpx — o que os consumidores da interface recebem."""

    status_code: int
    headers: dict[str, str] = field(default_factory=dict)
    content: bytes = b""

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        # Any: payload JSON de API externa é arbitrário por natureza (mesma
        # justificativa do payload de log em app/core/logging.py).
        return json.loads(self.content)


class HttpClientError(Exception):
    """Base de todos os erros da camada."""


class HttpRequestError(HttpClientError):
    """Falha de transporte (timeout, conexão) depois de esgotadas as tentativas."""

    def __init__(self, url: str, cause: BaseException) -> None:
        super().__init__(f"falha de transporte em {url}: {cause}")
        self.url = url
        self.cause = cause


class HttpStatusError(HttpClientError):
    """Status retentável (retry_on) que persistiu depois de esgotadas as tentativas."""

    def __init__(self, url: str, status_code: int) -> None:
        super().__init__(f"status {status_code} persistente em {url}")
        self.url = url
        self.status_code = status_code


class CircuitOpenError(HttpClientError):
    """Circuit breaker aberto para o host — falha imediata, sem tocar a rede."""

    def __init__(self, host: str) -> None:
        super().__init__(f"circuito aberto para {host}")
        self.host = host


class RateLimitExceededError(HttpClientError):
    """Token bucket do host vazio — o chamador deve reagendar, não insistir."""

    def __init__(self, host: str) -> None:
        super().__init__(f"rate limit excedido para {host}")
        self.host = host


class ResponseTooLargeError(HttpClientError):
    """Corpo de resposta acima do limite de 10 MB (spec 041, regra 9)."""

    def __init__(self, url: str, size: int) -> None:
        super().__init__(f"resposta de {url} excede o limite ({size} bytes)")
        self.url = url
        self.size = size


class FixtureMissingError(HttpClientError):
    """Modo replay sem fixture gravada — nunca cair na rede (spec 041, regra 7)."""

    def __init__(self, path: str) -> None:
        super().__init__(f"fixture ausente: {path}. Grave com HTTP_RECORD=1 contra a API real.")
        self.path = path
