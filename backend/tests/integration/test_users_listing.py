import uuid
from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.core.tokens import create_access_token
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


async def test_listagem_filtra_por_role(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(role=UserRole.ADMINISTRADOR)
    await make_user(tenant_id=administrador.tenant_id, role=UserRole.COLABORADOR)
    await make_user(tenant_id=administrador.tenant_id, role=UserRole.GESTOR)

    response = await client.get(
        "/api/v1/users", params={"role": "GESTOR"}, headers=_auth_header(administrador)
    )

    assert response.status_code == 200
    body = response.json()
    assert all(item["role"] == "GESTOR" for item in body["items"])
    assert body["total"] == len(body["items"])


async def test_listagem_filtra_por_status_inativo(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(role=UserRole.ADMINISTRADOR)
    inativo = await make_user(
        tenant_id=administrador.tenant_id, role=UserRole.COLABORADOR, is_active=False
    )
    await make_user(tenant_id=administrador.tenant_id, role=UserRole.COLABORADOR, is_active=True)

    response = await client.get(
        "/api/v1/users", params={"status": "inactive"}, headers=_auth_header(administrador)
    )

    assert response.status_code == 200
    body = response.json()
    ids = {item["id"] for item in body["items"]}
    assert str(inativo.user_id) in ids
    assert all(not item["is_active"] for item in body["items"])


async def test_listagem_filtra_por_busca_textual(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(role=UserRole.ADMINISTRADOR)
    alvo_email = f"maria-{uuid.uuid4()}@example.com"
    alvo = await make_user(
        tenant_id=administrador.tenant_id, role=UserRole.COLABORADOR, email=alvo_email
    )
    await make_user(tenant_id=administrador.tenant_id, role=UserRole.COLABORADOR)

    response = await client.get(
        "/api/v1/users", params={"q": alvo_email.split("@")[0]}, headers=_auth_header(administrador)
    )

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["items"]}
    assert str(alvo.user_id) in ids


async def test_listagem_pagina_por_cursor(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(role=UserRole.ADMINISTRADOR)
    for _ in range(3):
        await make_user(tenant_id=administrador.tenant_id, role=UserRole.COLABORADOR)

    first_page = await client.get(
        "/api/v1/users", params={"limit": 2}, headers=_auth_header(administrador)
    )
    assert first_page.status_code == 200
    first_body = first_page.json()
    assert len(first_body["items"]) == 2
    assert first_body["next_cursor"] is not None

    second_page = await client.get(
        "/api/v1/users",
        params={"limit": 2, "cursor": first_body["next_cursor"]},
        headers=_auth_header(administrador),
    )
    assert second_page.status_code == 200
    second_body = second_page.json()

    first_ids = {item["id"] for item in first_body["items"]}
    second_ids = {item["id"] for item in second_body["items"]}
    assert first_ids.isdisjoint(second_ids)


async def test_colaborador_nao_pode_listar(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador = await make_user(role=UserRole.COLABORADOR)

    response = await client.get("/api/v1/users", headers=_auth_header(colaborador))

    assert response.status_code == 403


async def test_tenant_a_nao_ve_usuarios_de_tenant_b_na_listagem(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    admin_a = await make_user(role=UserRole.ADMINISTRADOR)
    admin_b = await make_user(role=UserRole.ADMINISTRADOR)

    response = await client.get("/api/v1/users", headers=_auth_header(admin_a))

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["items"]}
    assert str(admin_b.user_id) not in ids
