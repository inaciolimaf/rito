"""Spec 102, Bloco C (regras 18-20): os três fluxos de autenticação passam a mandar
e-mail.

O canal é um fake que implementa `MessagingChannel` — a mesma interface do SMTP real
(CLAUDE.md §5, LSP: o mock é uma implementação real da interface). Nenhum e-mail sai em
teste, e nenhum socket é aberto.
"""

import uuid
from collections.abc import Awaitable, Callable, Generator

import pytest
from httpx import AsyncClient

from app.core.deps import get_transactional_email
from app.core.transactional_email import TransactionalEmailSender
from app.domain.users.models import UserRole
from app.integrations.messaging.base import ChannelNotConfiguredError
from app.main import app
from tests.integration.conftest import SeededUser, auth_header


class CanalFake:
    """Implementação de `MessagingChannel` que só guarda o que receberia."""

    def __init__(self, *, configurado: bool = True) -> None:
        self.configurado = configurado
        self.enviados: list[dict[str, str]] = []

    async def send(self, *, to: str, subject: str, message: str) -> None:
        if not self.configurado:
            raise ChannelNotConfiguredError("SMTP_HOST não configurado.")
        self.enviados.append({"to": to, "subject": subject, "message": message})


@pytest.fixture
def canal() -> Generator[Callable[..., CanalFake]]:
    """Instala o canal fake na dependência e devolve o espião."""
    instalados: list[CanalFake] = []

    def _instala(*, configurado: bool = True) -> CanalFake:
        fake = CanalFake(configurado=configurado)
        app.dependency_overrides[get_transactional_email] = lambda: TransactionalEmailSender(
            channel=fake, base_url="https://app.rito.test"
        )
        instalados.append(fake)
        return fake

    yield _instala
    app.dependency_overrides.pop(get_transactional_email, None)


async def test_forgot_password_envia_link_com_token(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    canal: Callable[..., CanalFake],
) -> None:
    """Regra 18: o e-mail sai com o link. Antes desta spec o token era gerado e
    descartado — o fluxo de recuperação de senha não tinha saída."""
    fake = canal()
    usuario = await make_user(role=UserRole.GESTOR)

    resposta = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": usuario.email},
        headers={"X-Tenant-Id": str(usuario.tenant_id)},
    )

    assert resposta.status_code == 202
    assert len(fake.enviados) == 1
    enviado = fake.enviados[0]
    assert enviado["to"] == usuario.email
    assert "https://app.rito.test/reset-password?token=" in enviado["message"]


async def test_forgot_password_de_email_inexistente_continua_202_e_nao_envia(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    canal: Callable[..., CanalFake],
) -> None:
    """Regra 18, segunda metade: a rota não pode virar oráculo de "esse e-mail existe".
    O status é o mesmo dos dois lados; o que muda é só o envio."""
    fake = canal()
    usuario = await make_user(role=UserRole.GESTOR)

    resposta = await client.post(
        "/api/v1/auth/forgot-password",
        json={"email": f"nao-existe-{uuid.uuid4().hex[:8]}@exemplo.com"},
        headers={"X-Tenant-Id": str(usuario.tenant_id)},
    )

    assert resposta.status_code == 202
    assert fake.enviados == []


async def test_convite_de_usuario_envia_link_e_nao_devolve_token(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    canal: Callable[..., CanalFake],
) -> None:
    """Regra 19."""
    fake = canal()
    gestor = await make_user(role=UserRole.GESTOR)
    convidado = f"convidado-{uuid.uuid4().hex[:8]}@exemplo.com"

    resposta = await client.post(
        "/api/v1/users/invite",
        json={"email": convidado, "name": "Convidado", "role": "COLABORADOR"},
        headers=auth_header(gestor),
    )

    assert resposta.status_code == 201, resposta.text
    assert "token" not in resposta.json()
    assert len(fake.enviados) == 1
    assert fake.enviados[0]["to"] == convidado
    assert "https://app.rito.test/accept-invite?token=" in fake.enviados[0]["message"]


async def test_convite_de_parceria_envia_link_e_nao_devolve_token(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    canal: Callable[..., CanalFake],
) -> None:
    """Regra 19: devolver o segredo no corpo da resposta era o contorno de não haver
    envio (spec 079), não o contrato."""
    fake = canal()
    gestor = await make_user(role=UserRole.GESTOR)
    parceiro = f"parceiro-{uuid.uuid4().hex[:8]}@exemplo.com"

    resposta = await client.post(
        "/api/v1/partnerships/invite",
        json={"email": parceiro},
        headers=auth_header(gestor),
    )

    assert resposta.status_code == 201, resposta.text
    assert "token" not in resposta.json()
    # `account_exists` continua — é o que distingue convite de parceria de convite de
    # cadastro (regra 2 da 079).
    assert "account_exists" in resposta.json()
    assert len(fake.enviados) == 1
    assert fake.enviados[0]["to"] == parceiro


async def test_sem_smtp_o_convite_continua_valendo(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    canal: Callable[..., CanalFake],
) -> None:
    """Regra 20: canal não configurado vira log, não erro. O token já foi criado e é
    válido — o que falhou foi a entrega, e derrubar a operação perderia o trabalho feito.
    """
    fake = canal(configurado=False)
    gestor = await make_user(role=UserRole.GESTOR)
    convidado = f"convidado-{uuid.uuid4().hex[:8]}@exemplo.com"

    resposta = await client.post(
        "/api/v1/users/invite",
        json={"email": convidado, "name": "Convidado", "role": "COLABORADOR"},
        headers=auth_header(gestor),
    )

    assert resposta.status_code == 201, resposta.text
    assert fake.enviados == []

    # E o convite existe de verdade: veio com id e validade persistidos. O token está
    # gravado e continua aceitável em /invitations/accept — o que falhou foi só a entrega.
    assert resposta.json()["id"]
    assert resposta.json()["expires_at"]
    assert resposta.json()["email"] == convidado
