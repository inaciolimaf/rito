"""Caminhos de erro de get_tenant_id (spec 004) — regra "todo caminho de erro tem teste"
da spec 010 (checklist de cobertura)."""

from httpx import AsyncClient


async def test_login_sem_x_tenant_id_retorna_400(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "alguem@example.com", "password": "qualquer-coisa"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Cabeçalho X-Tenant-Id é obrigatório."


async def test_login_com_x_tenant_id_invalido_retorna_400(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "alguem@example.com", "password": "qualquer-coisa"},
        headers={"X-Tenant-Id": "nao-e-um-uuid"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "X-Tenant-Id inválido."
