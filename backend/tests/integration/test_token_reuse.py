from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from tests.integration.conftest import SeededUser


async def test_reusing_a_revoked_refresh_token_revokes_whole_family(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user()
    headers = {"X-Tenant-Id": str(seeded.tenant_id)}

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": seeded.email, "password": seeded.password},
        headers=headers,
    )
    original_refresh_token = login_response.json()["refresh_token"]

    first_refresh = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": original_refresh_token},
        headers=headers,
    )
    assert first_refresh.status_code == 200
    rotated_refresh_token = first_refresh.json()["refresh_token"]

    # Reuso do token já revogado (o rotacionado na chamada anterior).
    reuse_response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": original_refresh_token},
        headers=headers,
    )
    assert reuse_response.status_code == 401

    # A família inteira devia ter sido revogada — o token que era válido também morre.
    rotated_now_dead = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": rotated_refresh_token},
        headers=headers,
    )
    assert rotated_now_dead.status_code == 401


async def test_inactive_user_does_not_authenticate(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user(is_active=False)

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": seeded.email, "password": seeded.password},
        headers={"X-Tenant-Id": str(seeded.tenant_id)},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "E-mail ou senha inválidos."
