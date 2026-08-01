from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.core.tokens import create_access_token
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser


async def test_colaborador_gets_403_on_gestor_route(
    rbac_client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user(role=UserRole.COLABORADOR)
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)

    response = await rbac_client.get(
        "/api/v1/rbac-test/gestor-only", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403
    assert "GESTOR" in response.json()["detail"]


async def test_gestor_accesses_administrador_route(
    rbac_client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user(role=UserRole.GESTOR)
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)

    response = await rbac_client.get(
        "/api/v1/rbac-test/administrador-or-above",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
