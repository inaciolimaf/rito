from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.auth.service import AuthService
from app.main import app
from tests.integration.conftest import SeededUser


async def _generate_reset_token(
    app_session_factory: async_sessionmaker[AsyncSession],
    redis: Redis,
    seeded: SeededUser,
) -> str:
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, seeded.tenant_id)
        service = AuthService(session=session, redis=redis, tenant_id=seeded.tenant_id)
        raw_token = await service.forgot_password(seeded.email)

    assert raw_token is not None
    return raw_token


async def test_password_reset_token_is_single_use(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seeded = await make_user()
    headers = {"X-Tenant-Id": str(seeded.tenant_id)}
    redis: Redis = app.state.redis

    raw_token = await _generate_reset_token(app_session_factory, redis, seeded)

    reset_response = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "password": "NovaSenha456!"},
        headers=headers,
    )
    assert reset_response.status_code == 204

    login_with_new_password = await client.post(
        "/api/v1/auth/login",
        json={"email": seeded.email, "password": "NovaSenha456!"},
        headers=headers,
    )
    assert login_with_new_password.status_code == 200

    reuse_response = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "password": "OutraSenha789!"},
        headers=headers,
    )
    assert reuse_response.status_code == 400


async def test_forgot_password_always_returns_202(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user()
    headers = {"X-Tenant-Id": str(seeded.tenant_id)}

    known_email_response = await client.post(
        "/api/v1/auth/forgot-password", json={"email": seeded.email}, headers=headers
    )
    unknown_email_response = await client.post(
        "/api/v1/auth/forgot-password", json={"email": "ninguem@example.com"}, headers=headers
    )

    assert known_email_response.status_code == 202
    assert unknown_email_response.status_code == 202


async def test_login_rate_limit_after_five_attempts(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user()
    headers = {"X-Tenant-Id": str(seeded.tenant_id)}

    for _ in range(5):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": seeded.email, "password": "senha-errada"},
            headers=headers,
        )
        assert response.status_code == 401

    sixth_attempt = await client.post(
        "/api/v1/auth/login",
        json={"email": seeded.email, "password": "senha-errada"},
        headers=headers,
    )
    assert sixth_attempt.status_code == 429
