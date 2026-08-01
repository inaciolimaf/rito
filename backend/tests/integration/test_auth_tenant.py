import uuid
from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from tests.integration.conftest import SeededUser


async def test_same_email_coexists_across_two_tenants(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    shared_email = f"{uuid.uuid4()}@example.com"
    tenant_a = await make_user(email=shared_email, password="SenhaA123!")
    tenant_b = await make_user(email=shared_email, password="SenhaB123!")

    assert tenant_a.tenant_id != tenant_b.tenant_id
    assert tenant_a.email == tenant_b.email

    login_a = await client.post(
        "/api/v1/auth/login",
        json={"email": shared_email, "password": "SenhaA123!"},
        headers={"X-Tenant-Id": str(tenant_a.tenant_id)},
    )
    assert login_a.status_code == 200

    login_b = await client.post(
        "/api/v1/auth/login",
        json={"email": shared_email, "password": "SenhaB123!"},
        headers={"X-Tenant-Id": str(tenant_b.tenant_id)},
    )
    assert login_b.status_code == 200

    # Senha de B não abre a conta de A no mesmo e-mail, e vice-versa.
    cross_attempt = await client.post(
        "/api/v1/auth/login",
        json={"email": shared_email, "password": "SenhaB123!"},
        headers={"X-Tenant-Id": str(tenant_a.tenant_id)},
    )
    assert cross_attempt.status_code == 401


async def test_access_token_only_resolves_its_own_tenant(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user()

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": seeded.email, "password": seeded.password},
        headers={"X-Tenant-Id": str(seeded.tenant_id)},
    )
    access_token = login_response.json()["access_token"]

    me_response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )

    assert me_response.status_code == 200
    body = me_response.json()
    assert body["tenant"] == str(seeded.tenant_id)
    assert body["id"] == str(seeded.user_id)
