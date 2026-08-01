import uuid
from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.core.tokens import create_access_token
from app.domain.users.models import FinancialAccess, UserRole
from tests.integration.conftest import SeededUser


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


def _valid_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Nome Atualizado",
        "role": "COLABORADOR",
        "financial_access": "NONE",
        "salary": "5000.00",
    }
    payload.update(overrides)
    return payload


async def test_usuario_nao_altera_o_proprio_role(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user(role=UserRole.COLABORADOR, financial_access=FinancialAccess.NONE)

    response = await client.put(
        f"/api/v1/users/{seeded.user_id}",
        json=_valid_payload(role="ADMINISTRADOR"),
        headers=_auth_header(seeded),
    )

    assert response.status_code == 403


async def test_usuario_altera_o_proprio_nome_sem_mudar_role(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user(role=UserRole.COLABORADOR, financial_access=FinancialAccess.NONE)

    response = await client.put(
        f"/api/v1/users/{seeded.user_id}",
        json=_valid_payload(name="Nome Novo"),
        headers=_auth_header(seeded),
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Nome Novo"


async def test_administrador_altera_role_de_outro_usuario(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(role=UserRole.ADMINISTRADOR)
    colaborador = await make_user(tenant_id=administrador.tenant_id, role=UserRole.COLABORADOR)

    response = await client.put(
        f"/api/v1/users/{colaborador.user_id}",
        json=_valid_payload(role="ADMINISTRADOR"),
        headers=_auth_header(administrador),
    )

    assert response.status_code == 200
    assert response.json()["role"] == "ADMINISTRADOR"


async def test_colaborador_nao_pode_editar_outro_usuario(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador_a = await make_user(role=UserRole.COLABORADOR)
    colaborador_b = await make_user(tenant_id=colaborador_a.tenant_id, role=UserRole.COLABORADOR)

    response = await client.put(
        f"/api/v1/users/{colaborador_b.user_id}",
        json=_valid_payload(),
        headers=_auth_header(colaborador_a),
    )

    assert response.status_code == 403


async def test_salario_oculto_para_financial_access_none(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(
        role=UserRole.ADMINISTRADOR, financial_access=FinancialAccess.NONE
    )
    colaborador = await make_user(tenant_id=administrador.tenant_id, role=UserRole.COLABORADOR)

    await client.put(
        f"/api/v1/users/{colaborador.user_id}",
        json=_valid_payload(salary="12345.67"),
        headers=_auth_header(administrador),
    )

    response = await client.get(
        f"/api/v1/users/{colaborador.user_id}", headers=_auth_header(administrador)
    )

    assert response.status_code == 200
    assert response.json()["salary"] is None


async def test_get_usuario_inexistente_retorna_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(role=UserRole.ADMINISTRADOR)

    response = await client.get(
        f"/api/v1/users/{uuid.uuid4()}", headers=_auth_header(administrador)
    )

    assert response.status_code == 404


async def test_put_usuario_inexistente_retorna_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(role=UserRole.ADMINISTRADOR)

    response = await client.put(
        f"/api/v1/users/{uuid.uuid4()}",
        json=_valid_payload(),
        headers=_auth_header(administrador),
    )

    assert response.status_code == 404


async def test_salario_visivel_para_financial_access_read_only(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(
        role=UserRole.ADMINISTRADOR, financial_access=FinancialAccess.READ_ONLY
    )
    colaborador = await make_user(tenant_id=administrador.tenant_id, role=UserRole.COLABORADOR)

    await client.put(
        f"/api/v1/users/{colaborador.user_id}",
        json=_valid_payload(salary="12345.67"),
        headers=_auth_header(administrador),
    )

    response = await client.get(
        f"/api/v1/users/{colaborador.user_id}", headers=_auth_header(administrador)
    )

    assert response.status_code == 200
    assert response.json()["salary"] == "12345.67"
