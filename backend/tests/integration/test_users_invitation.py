import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.core.tokens import create_access_token, generate_refresh_token
from app.domain.users.models import UserInvitation, UserRole
from app.domain.users.repository import UserInvitationRepository
from app.domain.users.schemas import InviteUserRequest
from app.domain.users.service import UserService
from tests.integration.conftest import SeededUser


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


async def _invite_and_get_raw_token(
    app_session_factory: async_sessionmaker[AsyncSession],
    *,
    actor: SeededUser,
    email: str,
) -> str:
    """Sem infra de e-mail ainda (mesma situação do forgot-password, spec 004) — o token
    bruto só existe fora do HTTP, chamando o service direto, igual
    test_password_reset.py::_generate_reset_token faz para reset de senha."""
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, actor.tenant_id)
        service = UserService(session=session, tenant_id=actor.tenant_id)
        actor_user = await service.users.get_by_id(actor.user_id)
        assert actor_user is not None
        _invitation, raw_token = await service.invite(
            actor=actor_user,
            payload=InviteUserRequest(email=email, role=UserRole.COLABORADOR),
        )
    return raw_token


async def test_convite_aceite_login(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    email = f"convidado-{uuid.uuid4()}@example.com"

    raw_token = await _invite_and_get_raw_token(app_session_factory, actor=gestor, email=email)

    accept_response = await client.post(
        "/api/v1/invitations/accept",
        json={"token": raw_token, "name": "Novo Colaborador", "password": "SenhaForte123!"},
        headers={"X-Tenant-Id": str(gestor.tenant_id)},
    )
    assert accept_response.status_code == 204

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "SenhaForte123!"},
        headers={"X-Tenant-Id": str(gestor.tenant_id)},
    )
    assert login_response.status_code == 200


async def test_aceite_com_senha_fraca_retorna_422(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    email = f"senha-fraca-{uuid.uuid4()}@example.com"

    raw_token = await _invite_and_get_raw_token(app_session_factory, actor=gestor, email=email)

    response = await client.post(
        "/api/v1/invitations/accept",
        json={"token": raw_token, "name": "Alguém", "password": "fraca"},
        headers={"X-Tenant-Id": str(gestor.tenant_id)},
    )

    assert response.status_code == 422


async def test_convite_expirado_retorna_400(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    raw_token, token_hash = generate_refresh_token()

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, gestor.tenant_id)
        await UserInvitationRepository(session).create(
            UserInvitation(
                tenant_id=gestor.tenant_id,
                email=f"expirado-{uuid.uuid4()}@example.com",
                role=UserRole.COLABORADOR,
                token_hash=token_hash,
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
                invited_by=gestor.user_id,
            )
        )

    response = await client.post(
        "/api/v1/invitations/accept",
        json={"token": raw_token, "name": "Alguém", "password": "SenhaForte123!"},
        headers={"X-Tenant-Id": str(gestor.tenant_id)},
    )

    assert response.status_code == 400


async def test_email_duplicado_no_tenant_retorna_409(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    existing = await make_user(tenant_id=gestor.tenant_id)

    response = await client.post(
        "/api/v1/users/invite",
        json={"email": existing.email, "role": "COLABORADOR", "financial_access": "NONE"},
        headers=_auth_header(gestor),
    )

    assert response.status_code == 409


async def test_mesmo_email_em_outro_tenant_e_aceito(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    tenant_a_gestor = await make_user(role=UserRole.GESTOR)
    tenant_b_gestor = await make_user(role=UserRole.GESTOR)
    shared_email = f"compartilhado-{uuid.uuid4()}@example.com"

    await make_user(tenant_id=tenant_a_gestor.tenant_id, email=shared_email)

    # O e-mail já existe no tenant A, mas convidar o MESMO e-mail no tenant B é permitido
    # (unicidade é por tenant, spec 004 regra 8).
    response = await client.post(
        "/api/v1/users/invite",
        json={"email": shared_email, "role": "COLABORADOR", "financial_access": "NONE"},
        headers=_auth_header(tenant_b_gestor),
    )

    assert response.status_code == 201


async def test_reenviar_convite_invalida_o_anterior(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
    client: AsyncClient,
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    email = f"reconvidado-{uuid.uuid4()}@example.com"

    first_raw_token = await _invite_and_get_raw_token(
        app_session_factory, actor=gestor, email=email
    )
    await _invite_and_get_raw_token(app_session_factory, actor=gestor, email=email)

    accept_with_old_token = await client.post(
        "/api/v1/invitations/accept",
        json={"token": first_raw_token, "name": "Alguém", "password": "SenhaForte123!"},
        headers={"X-Tenant-Id": str(gestor.tenant_id)},
    )

    assert accept_with_old_token.status_code == 400


async def test_convite_de_um_tenant_nao_e_aceito_com_header_de_outro(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tenant_a_gestor = await make_user(role=UserRole.GESTOR)
    tenant_b_gestor = await make_user(role=UserRole.GESTOR)
    email = f"isolamento-{uuid.uuid4()}@example.com"

    raw_token = await _invite_and_get_raw_token(
        app_session_factory, actor=tenant_a_gestor, email=email
    )

    response = await client.post(
        "/api/v1/invitations/accept",
        json={"token": raw_token, "name": "Alguém", "password": "SenhaForte123!"},
        headers={"X-Tenant-Id": str(tenant_b_gestor.tenant_id)},
    )

    assert response.status_code == 400
