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
from dataclasses import dataclass
from typing import NoReturn

import httpx
from opentelemetry.trace import SpanKind
from redis.asyncio import Redis

from app.core.invariants import not_none
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


def _default_jitter() -> float:
    """Fator aleatório do backoff, entre 0,5× e 1,5× (spec 041, regra 2).

    O `S311` fica silenciado na linha do `return`: isto não é uso criptográfico. O objetivo
    é descorrelacionar as retentativas de vários workers que falharam ao mesmo tempo;
    previsibilidade aqui não dá vantagem a ninguém, e `secrets` gastaria entropia do
    sistema para nada.

    Função nomeada em vez de `lambda` atribuído: aquele obrigava silenciar o `E731` junto,
    e trocar uma supressão por duas é o oposto do que a spec 115 faz.
    """
    # Aleatoriedade de espaçamento, não de segredo — ver a docstring acima.
    return random.uniform(0.5, 1.5)  # noqa: S311


@dataclass(frozen=True, slots=True)
class _Attempt:
    """O que identifica UMA tentativa, para auditoria e log (spec 121).

    Sete valores que viajam juntos do começo ao fim de uma chamada e não são decisão de
    ninguém — são a identidade dela. Como objeto, `_settle` recebe um parâmetro em vez de
    sete, e o log e o registro de auditoria passam a receber comprovadamente os mesmos
    dados, em vez de dois conjuntos montados à mão.
    """

    method: str
    url: str
    parsed: httpx.URL
    host: str
    tenant_id: uuid.UUID | None
    duration_ms: int
    number: int


def _raise_exhausted(
    url: str,
    breaker: CircuitBreaker,
    last_status: int | None,
    last_error: BaseException | None,
) -> NoReturn:
    """Todas as tentativas falharam: conta como falha do host e sobe o último estado real.

    O status vem antes do erro de propósito: se a última tentativa CHEGOU ao servidor e
    tomou 503, isso é mais informativo para quem lê o log do que o timeout de duas
    tentativas atrás. `on_failure` aqui é o que abre o circuito depois de N falhas
    seguidas — e é o único ponto onde ele é chamado, porque sair pelo `_settle` é sucesso.
    """
    breaker.on_failure()
    if last_status is not None:
        raise HttpStatusError(url, last_status)
    raise HttpRequestError(
        url, not_none(last_error, "sem status e sem erro o laço teria retornado antes")
    )


@dataclass(frozen=True, slots=True)
class _Call:
    """A requisição que o chamador pediu — imutável e igual em todas as tentativas.

    Separa o QUE se pede (isto) de COMO se pede (a política) e de o QUE ACONTECEU (o
    `_Attempt`). Sem isso, o laço de retry precisaria de onze parâmetros.
    """

    method: str
    url: str
    parsed: httpx.URL
    host: str
    tenant_id: uuid.UUID | None
    params: dict[str, str] | None
    content: bytes | None

    def attempt(self, duration_ms: int, number: int) -> "_Attempt":
        """Esta chamada, na tentativa `number`, que levou `duration_ms`."""
        return _Attempt(
            self.method, self.url, self.parsed, self.host, self.tenant_id, duration_ms, number
        )


class ResilientHttpClient:
    # `# noqa: PLR0913` (1 dos 2 que a spec 116 autoriza): estes onze parâmetros não são uma
    # função fazendo coisas demais — são as dependências injetadas de um cliente, e injetar
    # é a única coisa que este construtor faz. Cinco delas existem para o TESTE substituir
    # tempo e acaso (`sleep`, `jitter`, `clock`, `rng`, taxa de amostragem); agrupá-las num
    # objeto obrigaria a editar 15 chamadas de teste — que a §10 desta spec proíbe — para
    # tornar `sleep=_no_sleep` mais verboso. O cheiro que o PLR0913 procura é outro.
    def __init__(  # noqa: PLR0913
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
        self._jitter = jitter if jitter is not None else _default_jitter
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
            return await self._request_with_resilience(
                method, url, parsed, host, headers, params, content, tenant_id
            )

    async def _check_gate(self, host: str, policy: HostPolicy, breaker: CircuitBreaker) -> None:
        """As duas recusas que acontecem ANTES de tocar a rede (spec 106).

        Estavam no corpo de `_request_with_resilience`, misturadas com o laço de retry —
        e são de outra natureza: aqui não há tentativa nenhuma, a requisição simplesmente
        não acontece.
        """
        # Regra 5: circuito aberto falha imediato, sem tocar a rede.
        if not breaker.allow():
            raise CircuitOpenError(host)
        # Regra 4: rate limit por host, global entre workers (token bucket no Redis).
        if policy.rate_limit_per_minute is None:
            return
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

    async def _prepare_request(
        self, method: str, url: str, headers: dict[str, str] | None
    ) -> tuple[str, dict[str, str]]:
        """Chave de cache e cabeçalhos de revalidação condicional.

        Só GET tem cache; e o `If-None-Match`/`If-Modified-Since` só entra quando o
        chamador não mandou o seu — quem pediu explicitamente manda mais que o cache.
        """
        request_headers = dict(headers or {})
        if self._cache is None or method != "GET":
            return "", request_headers
        cache_key = cache_key_for(method, url)
        cached = await self._cache.get(cache_key)
        if cached is None:
            return cache_key, request_headers
        ja_enviados = {nome.lower() for nome in request_headers}
        if cached.etag and "if-none-match" not in ja_enviados:
            request_headers["If-None-Match"] = cached.etag
        if cached.last_modified and "if-modified-since" not in ja_enviados:
            request_headers["If-Modified-Since"] = cached.last_modified
        return cache_key, request_headers

    async def _wait_before_retry(
        self,
        policy: HostPolicy,
        attempt: int,
        total_attempts: int,
        retry_after: str | None = None,
    ) -> None:
        """A pausa entre uma tentativa e a próxima — e nenhuma pausa depois da última.

        As duas causas de retentativa (erro de transporte e status retentável) esperavam
        cada uma do seu jeito, com a mesma regra escrita duas vezes. A diferença real
        entre elas é só uma: o servidor pode ter mandado `Retry-After`, e aí a regra 3
        manda obedecer a ele em vez do backoff calculado. Erro de transporte não tem
        cabeçalho nenhum para ler, e cai no backoff pelo mesmo caminho.

        Não dormir depois da última tentativa importa: seria segurar o chamador por um
        atraso que não vai ser usado para nada.
        """
        if attempt >= total_attempts:
            return
        # Regra 3: Retry-After prevalece sobre o backoff calculado.
        pedido = self._parse_retry_after(retry_after)
        await self._sleep(pedido if pedido is not None else self._backoff(policy, attempt))

    async def _settle(
        self,
        attempt: _Attempt,
        *,
        breaker: CircuitBreaker,
        cache_key: str,
        raw: httpx.Response,
        body: bytes,
    ) -> HttpResponse:
        """A resposta final: sucesso, 304, ou 4xx não retentável.

        Regra 1: 4xx exceto 429 nunca é retentado — volta para o chamador decidir. Chegar
        aqui é o que fecha o circuito do host (`on_success`), e é o único caminho em que
        isso acontece: quem sai pelo laço saiu por falha.
        """
        breaker.on_success()
        response = await self._finalize(attempt.method, cache_key, raw, body)
        await self._record_success_sampled(
            attempt.tenant_id,
            attempt.host,
            attempt.method,
            attempt.parsed.path,
            attempt.duration_ms,
            attempt.number,
            raw.status_code,
        )
        logger.info(
            "http_request host=%s method=%s path=%s status=%s duration_ms=%d attempt=%d",
            attempt.host,
            attempt.method,
            attempt.parsed.path,
            raw.status_code,
            attempt.duration_ms,
            attempt.number,
        )
        return response

    async def _send(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, str] | None,
        content: bytes | None,
        timeout_s: float,
    ) -> tuple[httpx.Response, bytes]:
        """Uma ida à rede, com o corpo já lido e validado pelo teto da regra 9.

        Resposta e corpo saem juntos porque `_read_body` pode recusar (corpo grande) — e
        aí a exceção precisa subir de dentro do MESMO `try` da tentativa, para virar
        retentativa em vez de erro do chamador.
        """
        raw = await self._client.request(
            method,
            url,
            headers=headers,
            params=params,
            content=content,
            timeout=timeout_s,  # regra 10: timeout sempre explícito
        )
        return raw, await self._read_body(raw, url)

    def _elapsed_ms(self, started: float) -> int:
        """Milissegundos desde `started`, pelo relógio injetável do cliente."""
        return int((self._clock() - started) * 1000)

    async def _failed_attempt(
        self,
        attempt: _Attempt,
        *,
        policy: HostPolicy,
        total_attempts: int,
        motivo: str,
        retry_after: str | None = None,
    ) -> None:
        """Registra a tentativa que falhou e espera até a próxima.

        Os dois caminhos de retentativa — erro de transporte e status retentável — faziam
        exatamente isto, com os mesmos sete argumentos escritos duas vezes. A única
        diferença real é o `retry_after`, que só existe quando houve resposta com
        cabeçalho para ler.
        """
        await self._record_failure(
            attempt.tenant_id,
            attempt.host,
            attempt.method,
            attempt.parsed.path,
            attempt.duration_ms,
            attempt.number,
            motivo,
        )
        await self._wait_before_retry(policy, attempt.number, total_attempts, retry_after)

    async def _request_with_resilience(
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
        await self._check_gate(host, policy, breaker)
        cache_key, request_headers = await self._prepare_request(method, url, headers)
        return await self._retry_loop(
            _Call(method, url, parsed, host, tenant_id, params, content),
            policy=policy,
            breaker=breaker,
            cache_key=cache_key,
            request_headers=request_headers,
        )

    async def _retry_loop(
        self,
        call: _Call,
        *,
        policy: HostPolicy,
        breaker: CircuitBreaker,
        cache_key: str,
        request_headers: dict[str, str],
    ) -> HttpResponse:
        """As N tentativas, com o estado da última guardado para quando acabarem.

        `last_status` e `last_error` são o que sobe quando o laço termina sem resposta
        final — e são reatribuídos a cada volta de propósito: o que interessa a quem lê o
        erro é o ÚLTIMO estado real, não o primeiro.
        """
        last_error: BaseException | None = None
        last_status: int | None = None
        total_attempts = 1 + policy.max_retries

        for attempt in range(1, total_attempts + 1):
            started = self._clock()
            try:
                raw, body = await self._send(
                    call.method,
                    call.url,
                    headers=request_headers,
                    params=call.params,
                    content=call.content,
                    timeout_s=policy.timeout_s,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                # Regra 1: erro de transporte é transitório — retenta.
                last_error, last_status = exc, None
                await self._failed_attempt(
                    call.attempt(self._elapsed_ms(started), attempt),
                    policy=policy,
                    total_attempts=total_attempts,
                    motivo=str(exc),
                )
                continue

            last_error = None
            last_status = raw.status_code
            feita = call.attempt(self._elapsed_ms(started), attempt)

            if raw.status_code in policy.retry_on:
                await self._failed_attempt(
                    feita,
                    policy=policy,
                    total_attempts=total_attempts,
                    motivo=f"status {raw.status_code}",
                    retry_after=raw.headers.get("retry-after"),
                )
                continue

            return await self._settle(
                feita, breaker=breaker, cache_key=cache_key, raw=raw, body=body
            )

        _raise_exhausted(call.url, breaker, last_status, last_error)

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
