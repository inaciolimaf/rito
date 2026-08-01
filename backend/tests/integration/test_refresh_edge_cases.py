"""Caminhos de erro de AuthService.refresh (spec 004) — regra "todo caminho de erro tem
teste" da spec 010 (checklist de cobertura)."""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.core.tokens import generate_refresh_token, hash_token
from app.domain.auth.models import RefreshToken
from app.domain.auth.repository import RefreshTokenRepository
from tests.integration.conftest import SeededUser


async def test_refresh_com_token_desconhecido_retorna_401(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user()

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "token-que-nunca-existiu"},
        headers={"X-Tenant-Id": str(seeded.tenant_id)},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Refresh token inválido."


async def test_refresh_com_token_expirado_retorna_401(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seeded = await make_user()
    raw_token, token_hash = generate_refresh_token()

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, seeded.tenant_id)
        await RefreshTokenRepository(session).create(
            RefreshToken(
                tenant_id=seeded.tenant_id,
                user_id=seeded.user_id,
                token_hash=token_hash,
                family_id=uuid.uuid4(),
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": raw_token},
        headers={"X-Tenant-Id": str(seeded.tenant_id)},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Refresh token inválido."
    # Confere que o token bruto correto de fato batia com o hash — senão o 401
    # viria do caminho errado (stored is None) e o teste passaria por acidente.
    assert hash_token(raw_token) == token_hash
