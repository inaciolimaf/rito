from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.core.tokens import create_access_token
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


async def test_lista_os_27_estados(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)

    response = await client.get("/api/v1/states", headers=_auth_header(gestor))

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 27
    codes = {item["code"] for item in body}
    assert "SP" in codes
    assert "DF" in codes


async def test_cidades_filtram_por_estado(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)

    response = await client.get("/api/v1/cities", params={"state": "SP"}, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) > 0
    assert all(item["state_code"] == "SP" for item in body)


async def test_cidades_filtram_por_busca_textual(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)

    response = await client.get(
        "/api/v1/cities", params={"state": "SP", "q": "São Paulo"}, headers=headers
    )

    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert "São Paulo" in names


async def test_cidades_de_um_estado_nao_aparecem_em_outro(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)

    response = await client.get(
        "/api/v1/cities", params={"state": "RJ", "q": "São Paulo"}, headers=headers
    )

    assert response.status_code == 200
    assert response.json() == []
