"""Integração do client HTTP resiliente com Redis e Postgres reais (spec 041, §8).

Redis e Postgres locais são infra de teste, como nos demais testes do projeto —
a rede externa continua proibida (o transporte é o MockTransport do httpx).
"""

import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.redis import create_redis_client
from app.core.rls import set_tenant_context
from app.domain.external_requests.models import ExternalRequest
from app.integrations.http.audit import DbAuditSink
from app.integrations.http.client import ResilientHttpClient
from app.integrations.http.types import (
    HostPolicy,
    HttpRequestError,
    RateLimitExceededError,
)

SessionFactory = async_sessionmaker[AsyncSession]


@pytest.fixture
async def redis() -> AsyncGenerator[Redis]:
    client = create_redis_client()
    yield client
    await client.aclose()


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=b"ok")


async def _no_sleep(seconds: float) -> None:
    pass


def _unique_host() -> str:
    # Host único por teste: a chave do token bucket é por host, e o Redis de teste
    # é compartilhado entre os workers do pytest-xdist.
    return f"rl-{uuid.uuid4().hex}.test"


async def test_rate_limit_bloqueia_acima_do_teto(redis: Redis) -> None:
    host = _unique_host()
    policy = HostPolicy(rate_limit_per_minute=3, max_retries=0)
    client = ResilientHttpClient(
        transport=httpx.MockTransport(_ok),
        redis=redis,
        policies={host: policy},
        sleep=_no_sleep,
    )
    try:
        for _ in range(3):
            await client.request("GET", f"http://{host}/dados")
        with pytest.raises(RateLimitExceededError):
            await client.request("GET", f"http://{host}/dados")
    finally:
        await client.aclose()
        await redis.delete(f"http_rate:{host}")


async def test_rate_limit_e_compartilhado_entre_dois_clients(redis: Redis) -> None:
    """O bucket mora no Redis, não no processo: dois clients (dois workers) com a
    mesma política dividem o mesmo teto (regra 4)."""
    host = _unique_host()
    policy = HostPolicy(rate_limit_per_minute=3, max_retries=0)
    clients = [
        ResilientHttpClient(
            transport=httpx.MockTransport(_ok),
            redis=redis,
            policies={host: policy},
            sleep=_no_sleep,
        )
        for _ in range(2)
    ]
    try:
        await clients[0].request("GET", f"http://{host}/dados")
        await clients[0].request("GET", f"http://{host}/dados")
        await clients[1].request("GET", f"http://{host}/dados")
        with pytest.raises(RateLimitExceededError):
            await clients[1].request("GET", f"http://{host}/dados")
    finally:
        for client in clients:
            await client.aclose()
        await redis.delete(f"http_rate:{host}")


@pytest.mark.commits
async def test_falha_e_sempre_gravada_em_external_requests(
    app_session_factory: SessionFactory, admin_engine: AsyncEngine
) -> None:
    host = _unique_host()

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("fora do ar", request=request)

    sink = DbAuditSink(app_session_factory)
    client = ResilientHttpClient(
        transport=httpx.MockTransport(boom),
        audit=sink,
        default_policy=HostPolicy(max_retries=1),
        sleep=_no_sleep,
    )
    try:
        with pytest.raises(HttpRequestError):
            await client.request("GET", f"http://{host}/comunicacao")
    finally:
        await client.aclose()

    # admin_engine bypassa RLS: a verificação é sobre a persistência, não o isolamento.
    async with admin_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT host, method, path, attempt, error, status_code "
                    "FROM external_requests WHERE host = :host ORDER BY attempt"
                ),
                {"host": host},
            )
        ).all()

    assert len(rows) == 2  # uma linha por tentativa falha — falha nunca é amostrada
    assert [row.attempt for row in rows] == [1, 2]
    assert all(row.error and "fora do ar" in row.error for row in rows)
    assert all(row.status_code is None for row in rows)


async def test_sucesso_com_amostragem_zero_nao_grava(
    app_session_factory: SessionFactory, admin_engine: AsyncEngine
) -> None:
    host = _unique_host()
    client = ResilientHttpClient(
        transport=httpx.MockTransport(_ok),
        audit=DbAuditSink(app_session_factory),
        audit_success_sample_rate=0.0,
        sleep=_no_sleep,
    )
    try:
        await client.request("GET", f"http://{host}/dados")
    finally:
        await client.aclose()

    async with admin_engine.connect() as conn:
        count = (
            await conn.execute(
                text("SELECT count(*) FROM external_requests WHERE host = :host"),
                {"host": host},
            )
        ).scalar_one()
    assert count == 0


async def test_rls_tenant_nao_ve_linha_de_outro_tenant_mas_ve_linhas_de_sistema(
    app_session_factory: SessionFactory,
) -> None:
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    host = _unique_host()

    async with app_session_factory() as session, session.begin():
        # Linhas de tenant precisam dos tenants existindo (FK) — cria os dois.
        from app.core.models import Tenant

        session.add_all(
            [
                Tenant(id=tenant_a, slug=f"t-{tenant_a}", name="A"),
                Tenant(id=tenant_b, slug=f"t-{tenant_b}", name="B"),
            ]
        )

    async def insert(tenant_id: uuid.UUID | None, path: str) -> None:
        async with app_session_factory() as session, session.begin():
            if tenant_id is not None:
                await set_tenant_context(session, tenant_id)
            session.add(
                ExternalRequest(tenant_id=tenant_id, host=host, method="GET", path=path, attempt=1)
            )

    await insert(tenant_a, "/do-tenant-a")
    await insert(tenant_b, "/do-tenant-b")
    await insert(None, "/de-sistema")

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_a)
        paths = (
            (
                await session.execute(
                    text("SELECT path FROM external_requests WHERE host = :host ORDER BY path"),
                    {"host": host},
                )
            )
            .scalars()
            .all()
        )

    assert paths == ["/de-sistema", "/do-tenant-a"]
