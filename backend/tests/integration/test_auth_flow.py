import uuid
from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from tests.integration.conftest import SeededUser


async def test_login_refresh_logout_cycle(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user()
    headers = {"X-Tenant-Id": str(seeded.tenant_id)}

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": seeded.email, "password": seeded.password},
        headers=headers,
    )
    assert login_response.status_code == 200
    login_body = login_response.json()
    assert login_body["access_token"]
    assert login_body["refresh_token"]
    assert login_body["expires_in"] == 15 * 60

    me_response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login_body['access_token']}"},
    )
    assert me_response.status_code == 200
    me_body = me_response.json()
    assert me_body["email"] == seeded.email
    assert me_body["tenant"] == str(seeded.tenant_id)

    refresh_response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login_body["refresh_token"]},
        headers=headers,
    )
    assert refresh_response.status_code == 200
    refresh_body = refresh_response.json()
    assert refresh_body["refresh_token"] != login_body["refresh_token"]

    logout_response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_body["refresh_token"]},
        headers=headers,
    )
    assert logout_response.status_code == 204

    reuse_after_logout = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_body["refresh_token"]},
        headers=headers,
    )
    assert reuse_after_logout.status_code == 401


async def test_wrong_password_returns_generic_401(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user()

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": seeded.email, "password": "senha-errada"},
        headers={"X-Tenant-Id": str(seeded.tenant_id)},
    )

    assert response.status_code == 401
    body = response.json()
    assert body["detail"] == "E-mail ou senha inválidos."


async def test_unknown_email_returns_same_generic_401(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "ninguem@example.com", "password": "qualquer-coisa"},
        headers={"X-Tenant-Id": str(uuid.uuid4())},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "E-mail ou senha inválidos."
