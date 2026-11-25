from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.core.tokens import create_access_token
from app.domain.users.models import FinancialAccess, UserRole
from tests.integration.conftest import SeededUser


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


async def test_none_gets_403_on_financial_read(
    rbac_client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user(financial_access=FinancialAccess.NONE)

    response = await rbac_client.get(
        "/api/v1/rbac-test/financial-read", headers=_auth_header(seeded)
    )

    assert response.status_code == 403


async def test_read_only_can_get_but_not_post(
    rbac_client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user(financial_access=FinancialAccess.READ_ONLY)
    headers = _auth_header(seeded)

    get_response = await rbac_client.get("/api/v1/rbac-test/financial-read", headers=headers)
    assert get_response.status_code == 200

    post_response = await rbac_client.post("/api/v1/rbac-test/financial-write", headers=headers)
    assert post_response.status_code == 403


async def test_full_can_write(
    rbac_client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user(financial_access=FinancialAccess.FULL)

    response = await rbac_client.post(
        "/api/v1/rbac-test/financial-write", headers=_auth_header(seeded)
    )

    assert response.status_code == 200


async def test_colaborador_with_full_financial_access_can_write(
    rbac_client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Ortogonal ao perfil (regra 2): Colaborador com FULL acessa financeiro."""
    seeded = await make_user(role=UserRole.COLABORADOR, financial_access=FinancialAccess.FULL)

    response = await rbac_client.post(
        "/api/v1/rbac-test/financial-write", headers=_auth_header(seeded)
    )

    assert response.status_code == 200


async def test_gestor_with_no_financial_access_is_blocked(
    rbac_client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Ortogonal ao perfil (regra 2): Gestor com NONE é barrado no financeiro."""
    seeded = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.NONE)

    response = await rbac_client.get(
        "/api/v1/rbac-test/financial-read", headers=_auth_header(seeded)
    )

    assert response.status_code == 403


async def test_o_403_do_financeiro_diz_qual_acesso_falta(
    rbac_client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """A mensagem é o produto do 403, não um detalhe (spec 132).

    Os testes acima conferem só o código de status, e a medição de mutação da 132 mostrou o
    efeito: apagar os dois pedaços literais da frase de `require_financial` deixava a suíte
    verde. Quem toma o 403 é um usuário do escritório, e "403" sozinho não diz o que pedir
    ao gestor.
    """
    seeded = await make_user(financial_access=FinancialAccess.READ_ONLY)

    response = await rbac_client.post(
        "/api/v1/rbac-test/financial-write", headers=_auth_header(seeded)
    )

    assert response.status_code == 403
    assert (
        response.json()["detail"]
        == f"Exige acesso financeiro {FinancialAccess.FULL.value} ou superior."
    )
