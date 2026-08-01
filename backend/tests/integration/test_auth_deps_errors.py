"""Caminhos de erro de get_current_user (spec 004) — regra "todo caminho de erro tem teste"
da spec 010 (checklist de cobertura)."""

from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.core.tokens import create_access_token
from tests.integration.conftest import SeededUser


async def test_me_sem_authorization_retorna_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Não autenticado."


async def test_me_com_token_invalido_retorna_401(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer token-forjado-e-invalido"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Token inválido ou expirado."


async def test_me_com_usuario_inativo_retorna_401(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user(is_active=False)

    # Login já bloqueia usuário inativo (spec 004) — para provar o caminho de
    # get_current_user (não o de login), o teste precisa de um access token
    # válido de um usuário que já nasce inativo. Como não há endpoint de
    # desativação ainda (chega em spec futura), assinamos o token diretamente
    # com create_access_token, igual o login faria.
    access_token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)

    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Usuário não encontrado ou inativo."
