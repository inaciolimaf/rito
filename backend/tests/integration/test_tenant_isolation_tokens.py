"""CLAUDE.md §4: "teste obrigatório por tabela nova: tenant A não enxerga dado de
tenant B" — refresh_tokens e password_reset_tokens ainda não tinham essa prova direta
(spec 010, checklist de cobertura). token_hash é globalmente único, então sem RLS a
query "funcionaria" mesmo vindo do tenant errado; é a política de RLS (FORCE ROW LEVEL
SECURITY) que precisa barrar isso, não um WHERE tenant_id manual (proibido pelo §4)."""

from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.auth.service import AuthService
from app.main import app
from tests.integration.conftest import SeededUser


async def test_refresh_token_de_um_tenant_nao_funciona_com_header_de_outro(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    tenant_a_user = await make_user()
    tenant_b_user = await make_user()

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": tenant_a_user.email, "password": tenant_a_user.password},
        headers={"X-Tenant-Id": str(tenant_a_user.tenant_id)},
    )
    refresh_token = login.json()["refresh_token"]

    cross_tenant_refresh = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
        headers={"X-Tenant-Id": str(tenant_b_user.tenant_id)},
    )

    assert cross_tenant_refresh.status_code == 401
    assert cross_tenant_refresh.json()["detail"] == "Refresh token inválido."


async def test_password_reset_token_de_um_tenant_nao_funciona_com_header_de_outro(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tenant_a_user = await make_user()
    tenant_b_user = await make_user()
    redis: Redis = app.state.redis

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_a_user.tenant_id)
        service = AuthService(session=session, redis=redis, tenant_id=tenant_a_user.tenant_id)
        raw_token = await service.forgot_password(tenant_a_user.email)
    assert raw_token is not None

    cross_tenant_reset = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "password": "NovaSenhaValida123!"},
        headers={"X-Tenant-Id": str(tenant_b_user.tenant_id)},
    )

    assert cross_tenant_reset.status_code == 400
    assert cross_tenant_reset.json()["detail"] == "Token inválido ou expirado."
