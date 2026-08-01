import uuid
from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.core.tokens import create_access_token
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


async def test_inativar_ultimo_gestor_retorna_409(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)

    response = await client.post(
        f"/api/v1/users/{gestor.user_id}/deactivate", headers=_auth_header(gestor)
    )

    assert response.status_code == 409


async def test_inativar_gestor_quando_ha_outro_ativo_funciona(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    first_gestor = await make_user(role=UserRole.GESTOR)
    second_gestor = await make_user(tenant_id=first_gestor.tenant_id, role=UserRole.GESTOR)

    response = await client.post(
        f"/api/v1/users/{first_gestor.user_id}/deactivate",
        headers=_auth_header(second_gestor),
    )

    assert response.status_code == 204


async def test_inativar_colaborador_nao_tem_a_restricao_do_ultimo_gestor(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    colaborador = await make_user(tenant_id=gestor.tenant_id, role=UserRole.COLABORADOR)

    response = await client.post(
        f"/api/v1/users/{colaborador.user_id}/deactivate", headers=_auth_header(gestor)
    )

    assert response.status_code == 204


async def test_inativar_usuario_inexistente_retorna_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)

    response = await client.post(
        f"/api/v1/users/{uuid.uuid4()}/deactivate", headers=_auth_header(gestor)
    )

    assert response.status_code == 404


async def test_colaborador_nao_pode_inativar(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    colaborador = await make_user(tenant_id=gestor.tenant_id, role=UserRole.COLABORADOR)

    response = await client.post(
        f"/api/v1/users/{gestor.user_id}/deactivate", headers=_auth_header(colaborador)
    )

    assert response.status_code == 403
