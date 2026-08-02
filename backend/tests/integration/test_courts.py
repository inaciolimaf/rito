from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.core.tokens import create_access_token
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


async def test_lista_os_182_tribunais(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador = await make_user(role=UserRole.COLABORADOR)

    response = await client.get("/api/v1/courts", headers=_auth_header(colaborador))

    assert response.status_code == 200
    assert len(response.json()) == 182


async def test_lista_os_13_sistemas(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador = await make_user(role=UserRole.COLABORADOR)

    response = await client.get("/api/v1/court-systems", headers=_auth_header(colaborador))

    assert response.status_code == 200
    assert len(response.json()) == 13


async def test_busca_por_sigla_exata(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador = await make_user(role=UserRole.COLABORADOR)

    response = await client.get(
        "/api/v1/courts", params={"q": "tjsp"}, headers=_auth_header(colaborador)
    )

    assert response.status_code == 200
    codes = {item["code"] for item in response.json()}
    assert "TJSP" in codes


async def test_busca_por_nome_parcial_sem_acento(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador = await make_user(role=UserRole.COLABORADOR)

    response = await client.get(
        "/api/v1/courts", params={"q": "parana"}, headers=_auth_header(colaborador)
    )

    assert response.status_code == 200
    codes = {item["code"] for item in response.json()}
    assert "TJPR" in codes


async def test_filtro_por_segmento(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador = await make_user(role=UserRole.COLABORADOR)

    response = await client.get(
        "/api/v1/courts", params={"segment": "SUPERIOR"}, headers=_auth_header(colaborador)
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 5
    assert all(item["segment"] == "SUPERIOR" for item in body)


async def test_filtro_por_uf(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador = await make_user(role=UserRole.COLABORADOR)

    response = await client.get(
        "/api/v1/courts", params={"state": "sp"}, headers=_auth_header(colaborador)
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) > 0
    assert all(item["state_code"] == "SP" for item in body)


async def test_superiores_sem_uf(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador = await make_user(role=UserRole.COLABORADOR)

    response = await client.get(
        "/api/v1/courts", params={"q": "stf"}, headers=_auth_header(colaborador)
    )

    assert response.status_code == 200
    body = response.json()
    assert body[0]["state_code"] is None
