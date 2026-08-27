"""Client HTTP resiliente (spec 041).

Ordem das camadas em cada chamada: circuit breaker → rate limit → cache
condicional (GET) → tentativas com retry/backoff → auditoria. Todas as
dependências de infra (transporte httpx, Redis, sink de auditoria, relógio,
sleep, jitter) são injetadas no construtor — DIP (CLAUDE.md §5) e é o que
permite testar tudo sem rede e sem dormir.
"""

import asyncio
import logging
import random
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping

import httpx
from opentelemetry.trace import SpanKind
from redis.asyncio import Redis

from app.core.observability.tracing import get_tracer
from app.core.rate_limit import check_and_increment
from app.integrations.http.audit import AuditSink, NullAuditSink, RequestAuditEntry
from app.integrations.http.breaker import CircuitBreaker, CircuitState
from app.integrations.http.cache import CacheStore, cache_key_for
from app.integrations.http.types import (
    CircuitOpenError,
    HostPolicy,
    HttpRequestError,
    HttpResponse,
    HttpStatusError,
    RateLimitExceededError,
    ResponseTooLargeError,
)

logger = logging.getLogger("rito.http")

# Spec 041, regra 9: corpo de resposta acima disso é rejeitado.
MAX_BODY_BYTES = 10 * 1024 * 1024

_RATE_LIMIT_WINDOW_S = 60


class ResilientHttpClient:
    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        redis: Redis | None = None,
        audit: AuditSink | None = None,
        cache: CacheStore | None = None,
        policies: Mapping[str, HostPolicy] | None = None,
        default_policy: HostPolicy | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] | None = None,
        clock: Callable[[], float] = time.monotonic,
        audit_success_sample_rate: float = 0.1,
        rng: Callable[[], float] = random.random,
    ) -> None:
        self._client = httpx.AsyncClient(transport=transport)
        self._redis = redis
        self._audit: AuditSink = audit if audit is not None else NullAuditSink()
        self._cache = cache
        self._policies = dict(policies or {})
        self._default_policy = default_policy or HostPolicy()
        self._sleep = sleep
        self._jitter = jitter if jitter is not None else lambda: random.uniform(0.5, 1.5)
        self._clock = clock
        self._audit_success_sample_rate = audit_success_sample_rate
        self._rng = rng
        self._breakers: dict[str, CircuitBreaker] = {}

    async def aclose(self) -> None:
        await self._client.aclose()

    def breaker_state(self, host: str) -> CircuitState:
        """Estado atual do circuito do host (observabilidade; painel da spec 049)."""
        breaker = self._breakers.get(host)
        return breaker.state if breaker is not None else CircuitState.CLOSED

    def _policy_for(self, host: str) -> HostPolicy:
        return self._policies.get(host, self._default_policy)

    def _breaker_for(self, host: str, policy: HostPolicy) -> CircuitBreaker:
        if host not in self._breakers:
            self._breakers[host] = CircuitBreaker(
                failure_threshold=policy.breaker_failure_threshold,
                reset_after_s=policy.breaker_reset_after_s,
                clock=self._clock,
            )
        return self._breakers[host]

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        content: bytes | None = None,
        tenant_id: uuid.UUID | None = None,
    ) -> HttpResponse:
        method = method.upper()
        parsed = httpx.URL(url)
        host = parsed.host or "unknown"
        # Spec 097, regra 4: o span de chamada externa nasce aqui, envolvendo breaker,
        # rate limit, cache e retries — é o tempo que o CHAMADOR espera, que é o que a
        # investigação de lentidão precisa ver. Um span por tentativa esconderia isso.
        with get_tracer().start_as_current_span(
            f"http {method}",
            kind=SpanKind.CLIENT,
            attributes={"http.request.method": method, "server.address": host},
        ):
            return await self._request_com_resiliencia(
                method, url, parsed, host, headers, params, content, tenant_id
            )

    async def _request_com_resiliencia(
        self,
        method: str,
        url: str,
        parsed: httpx.URL,
        host: str,
        headers: dict[str, str] | None,
        params: dict[str, str] | None,
        content: bytes | None,
        tenant_id: uuid.UUID | None,
    ) -> HttpResponse:
        policy = self._policy_for(host)
        breaker = self._breaker_for(host, policy)

        # Regra 5: circuito aberto falha imediato, sem tocar a rede.
        if not breaker.allow():
            raise CircuitOpenError(host)

        # Regra 4: rate limit por host, global entre workers (token bucket no Redis).
        if policy.rate_limit_per_minute is not None:
            if self._redis is None:
                raise RuntimeError(f"política de {host} exige Redis para rate limit")
            allowed = await check_and_increment(
                self._redis,
                f"http_rate:{host}",
                limit=policy.rate_limit_per_minute,
                window_seconds=_RATE_LIMIT_WINDOW_S,
            )
            if not allowed:
                raise RateLimitExceededError(host)

        request_headers = dict(headers or {})
        cache_key = ""
        if self._cache is not None and method == "GET":
            cache_key = cache_key_for(method, url)
            cached = await self._cache.get(cache_key)
            if cached is not None:
                # Regra implícita do escopo: revalidação condicional com os
                # validadores que o servidor deu da última vez.
                if cached.etag and "if-none-match" not in {k.lower() for k in request_headers}:
                    request_headers["If-None-Match"] = cached.etag
                if cached.last_modified and "if-modified-since" not in {
                    k.lower() for k in request_headers
                }:
                    request_headers["If-Modified-Since"] = cached.last_modified

        last_error: BaseException | None = None
        last_status: int | None = None
        total_attempts = 1 + policy.max_retries

        for attempt in range(1, total_attempts + 1):
            started = self._clock()
            try:
                raw = await self._client.request(
                    method,
                    url,
                    headers=request_headers,
                    params=params,
                    content=content,
                    timeout=policy.timeout_s,  # regra 10: timeout sempre explícito
                )
                body = await self._read_body(raw, url)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                # Regra 1: erro de transporte é transitório — retenta.
                duration_ms = int((self._clock() - started) * 1000)
                last_error = exc
                last_status = None
                await self._record_failure(
                    tenant_id, host, method, parsed.path, duration_ms, attempt, str(exc)
                )
                if attempt < total_attempts:
                    await self._sleep(self._backoff(policy, attempt))
                continue

            duration_ms = int((self._clock() - started) * 1000)
            last_error = None
            last_status = raw.status_code

            if raw.status_code in policy.retry_on:
                await self._record_failure(
                    tenant_id,
                    host,
                    method,
                    parsed.path,
                    duration_ms,
                    attempt,
                    f"status {raw.status_code}",
                )
                if attempt < total_attempts:
                    # Regra 3: Retry-After prevalece sobre o backoff calculado.
                    retry_after = self._parse_retry_after(raw.headers.get("retry-after"))
                    delay = (
                        retry_after if retry_after is not None else self._backoff(policy, attempt)
                    )
                    await self._sleep(delay)
                continue

            # Resposta final (sucesso, 304 ou 4xx não retentável — regra 1: 4xx
            # exceto 429 nunca é retentado, volta para o chamador decidir).
            breaker.on_success()
            response = await self._finalize(method, cache_key, raw, body)
            await self._record_success_sampled(
                tenant_id, host, method, parsed.path, duration_ms, attempt, raw.status_code
            )
            logger.info(
                "http_request host=%s method=%s path=%s status=%s duration_ms=%d attempt=%d",
                host,
                method,
                parsed.path,
                raw.status_code,
                duration_ms,
                attempt,
            )
            return response

        # Esgotou as tentativas: conta como falha do host para o breaker.
        breaker.on_failure()
        if last_status is not None:
            raise HttpStatusError(url, last_status)
        assert last_error is not None
        raise HttpRequestError(url, last_error)

    async def _read_body(self, raw: httpx.Response, url: str) -> bytes:
        # Regra 9: rejeita corpo grande — primeiro pelo header (antes de baixar),
        # depois pelo tamanho real lido.
        content_length = raw.headers.get("content-length")
        if content_length is not None and int(content_length) > MAX_BODY_BYTES:
            raise ResponseTooLargeError(url, int(content_length))
        body = await raw.aread()
        if len(body) > MAX_BODY_BYTES:
            raise ResponseTooLargeError(url, len(body))
        return body

    async def _finalize(
        self,
        method: str,
        cache_key: str,
        raw: httpx.Response,
        body: bytes,
    ) -> HttpResponse:
        response = HttpResponse(
            status_code=raw.status_code, headers=dict(raw.headers), content=body
        )
        if self._cache is None or method != "GET":
            return response
        if raw.status_code == 304:
            cached = await self._cache.get(cache_key)
            if cached is not None:
                return HttpResponse(status_code=200, headers=cached.headers, content=cached.body)
            return response
        if raw.status_code == 200 and ("etag" in raw.headers or "last-modified" in raw.headers):
            await self._cache.store(
                cache_key,
                etag=raw.headers.get("etag"),
                last_modified=raw.headers.get("last-modified"),
                headers=dict(raw.headers),
                body=body,
            )
        return response

    def _backoff(self, policy: HostPolicy, attempt: int) -> float:
        # Regra 2: base × 2^(tentativa-1) × jitter(0.5–1.5), teto de 30 s.
        delay: float = policy.backoff_base_s * (2 ** (attempt - 1)) * self._jitter()
        return min(policy.backoff_cap_s, delay)

    @staticmethod
    def _parse_retry_after(value: str | None) -> float | None:
        if value is None:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            # Formato HTTP-date é raro nas APIs públicas brasileiras; se vier,
            # cai no backoff calculado em vez de adivinhar.
            return None

    async def _record_failure(
        self,
        tenant_id: uuid.UUID | None,
        host: str,
        method: str,
        path: str,
        duration_ms: int,
        attempt: int,
        error: str,
    ) -> None:
        # Regra 6: falha é SEMPRE gravada.
        await self._audit.record(
            RequestAuditEntry(
                tenant_id=tenant_id,
                host=host,
                method=method,
                path=path,
                status_code=None,
                duration_ms=duration_ms,
                attempt=attempt,
                error=error,
            )
        )

    async def _record_success_sampled(
        self,
        tenant_id: uuid.UUID | None,
        host: str,
        method: str,
        path: str,
        duration_ms: int,
        attempt: int,
        status_code: int,
    ) -> None:
        # Regra 6: sucesso pode ser amostrado.
        if self._rng() >= self._audit_success_sample_rate:
            return
        await self._audit.record(
            RequestAuditEntry(
                tenant_id=tenant_id,
                host=host,
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
                attempt=attempt,
                error=None,
            )
        )

    async def stream_lines(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
        timeout_s: float | None = None,
    ) -> AsyncIterator[str]:
        """Resposta linha a linha, para SSE (spec 081, regra 8).

        Deliberadamente FORA das camadas de retry e cache: uma resposta já
        parcialmente entregue não pode ser reenviada de forma transparente — quem
        consome decide o que fazer com o erro no meio do stream. O breaker continua
        valendo (não faz sentido abrir stream para host derrubado) e a falha conta
        para ele, como em qualquer outra chamada.
        """
        method = method.upper()
        parsed = httpx.URL(url)
        host = parsed.host or "unknown"
        policy = self._policy_for(host)
        breaker = self._breaker_for(host, policy)
        if not breaker.allow():
            raise CircuitOpenError(host)

        # Spec 097, regra 4: o span cobre o stream INTEIRO, não só a abertura da
        # conexão — num SSE de LLM o que interessa medir é quanto tempo a resposta
        # levou para terminar de chegar.
        span = get_tracer().start_span(
            f"http {method}",
            kind=SpanKind.CLIENT,
            attributes={"http.request.method": method, "server.address": host},
        )
        request = self._client.build_request(
            method, url, headers=headers, content=content, timeout=timeout_s or policy.timeout_s
        )
        try:
            try:
                response = await self._client.send(request, stream=True)
            except httpx.HTTPError as exc:
                breaker.on_failure()
                raise HttpRequestError(url, exc) from exc
            try:
                if response.status_code >= 500:
                    breaker.on_failure()
                    raise HttpStatusError(url, response.status_code)
                breaker.on_success()
                async for line in response.aiter_lines():
                    yield line
            finally:
                await response.aclose()
        finally:
            span.end()


def create_http_client(
    *,
    redis: Redis | None = None,
    audit: AuditSink | None = None,
    cache: CacheStore | None = None,
    policies: Mapping[str, HostPolicy] | None = None,
) -> ResilientHttpClient:
    """Monta o client de produção: em `app_env=test`, o transporte vira replay de
    fixtures (ou gravação, com HTTP_RECORD=1) — nunca rede de verdade."""
    from pathlib import Path

    from app.core.config import get_settings
    from app.integrations.http.fixtures import FixtureTransport

    settings = get_settings()
    transport: httpx.AsyncBaseTransport | None = None
    if settings.app_env == "test":
        transport = FixtureTransport(Path(settings.http_fixtures_dir), record=settings.http_record)
    return ResilientHttpClient(
        transport=transport, redis=redis, audit=audit, cache=cache, policies=policies
    )
