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


async def test_administrador_gets_403_on_gestor_route(
    rbac_client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """O degrau do MEIO da hierarquia (spec 132).

    Os dois testes acima cobrem só os extremos: Colaborador barrado no topo e Gestor
    passando no meio. Nenhum deles distingue ADMINISTRADOR de GESTOR — trocar o ordinal de
    um dos dois em `_ROLE_ORDER` empatava os perfis e deixava um Administrador entrar em
    rota de Gestor com a suíte inteira verde. A medição de mutação da 132 achou isso como
    quatro mutantes sobreviventes; este teste e o de baixo matam os quatro.

    A mensagem é comparada por igualdade, e não por `in`: ela vai para a tela de quem tomou
    o 403, e "GESTOR" sozinho passa mesmo com o resto da frase apagado.
    """
    seeded = await make_user(role=UserRole.ADMINISTRADOR)
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)

    response = await rbac_client.get(
        "/api/v1/rbac-test/gestor-only", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403
    assert response.json()["detail"] == f"Exige perfil {UserRole.GESTOR.value} ou superior."


async def test_colaborador_gets_403_on_administrador_route(
    rbac_client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """O outro degrau: Colaborador barrado no nível intermediário, não só no topo."""
    seeded = await make_user(role=UserRole.COLABORADOR)
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)

    response = await rbac_client.get(
        "/api/v1/rbac-test/administrador-or-above",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == f"Exige perfil {UserRole.ADMINISTRADOR.value} ou superior."
