"""Camada única de saída HTTP (spec 041).

DJEN e DataJud são APIs públicas sem SLA — toda a resiliência (retry, rate limit,
circuit breaker, cache condicional, fixtures de teste) mora aqui, nunca espalhada
nos clients de cada integração.
"""

from app.integrations.http.client import ResilientHttpClient, create_http_client
from app.integrations.http.types import (
    CircuitOpenError,
    FixtureMissingError,
    HostPolicy,
    HttpClientError,
    HttpRequestError,
    HttpResponse,
    HttpStatusError,
    RateLimitExceededError,
    ResponseTooLargeError,
)

__all__ = [
    "CircuitOpenError",
    "FixtureMissingError",
    "HostPolicy",
    "HttpClientError",
    "HttpRequestError",
    "HttpResponse",
    "HttpStatusError",
    "RateLimitExceededError",
    "ResilientHttpClient",
    "ResponseTooLargeError",
    "create_http_client",
]
