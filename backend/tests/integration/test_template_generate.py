"""Modelos: geração e envio (spec 067, §8) — PDF via HTTP, salvar na nuvem do
processo (com quota) e envio de e-mail direto no service (mailer fake, mesmo padrão
de `FakeEmailChannel` em `test_dunning.py` — nunca SMTP real em teste)."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.core.tokens import create_access_token
from app.domain.account.models import AccountPlan
from app.domain.documents import quota
from app.domain.templates.generate import TemplateGenerationService
from app.domain.templates.models import Template, TemplateType
from app.domain.users.models import User, UserRole
from app.integrations.messaging.base import ChannelNotConfiguredError
from app.integrations.storage.s3 import create_file_storage
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import _create_lawsuit, _create_lawsuit_type, _create_stage

SessionFactory = async_sessionmaker[AsyncSession]


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


async def _create_template(client: AsyncClient, headers: dict[str, str], **extra: object) -> str:
    payload: dict[str, object] = {
        "name": "Contrato de honorários",
        "type": "CONTRATO",
        "content": "<p>Corpo do contrato</p>",
        **extra,
    }
    response = await client.post("/api/v1/templates", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    result: str = response.json()["id"]
    return result


async def test_generate_pdf_devolve_pdf_nao_vazio(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(user)
    template_id = await _create_template(client, headers)

    response = await client.post(
        f"/api/v1/templates/{template_id}/generate-pdf", json={}, headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


async def test_save_to_cloud_sem_lawsuit_id_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(user)
    template_id = await _create_template(client, headers)

    response = await client.post(
        f"/api/v1/templates/{template_id}/save-to-cloud", json={}, headers=headers
    )
    assert response.status_code == 422


async def test_save_to_cloud_com_lawsuit_id_cria_documento_na_nuvem_do_processo(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(user)
    template_id = await _create_template(client, headers, name="Petição salva")

    lawsuit_type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    lawsuit = await _create_lawsuit(
        client,
        headers,
        user_id=str(user.user_id),
        lawsuit_type_id=lawsuit_type_id,
        stage_id=stage_id,
    )
    lawsuit_id = str(lawsuit["id"])

    response = await client.post(
        f"/api/v1/templates/{template_id}/save-to-cloud",
        json={"lawsuit_id": lawsuit_id},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["filename"] == "Petição salva.pdf"
    assert body["content_type"] == "application/pdf"

    listing = await client.get(
        "/api/v1/documents",
        params={"scope_type": "LAWSUIT", "scope_id": lawsuit_id},
        headers=headers,
    )
    names = [item["filename"] for item in listing.json()["documents"]]
    assert "Petição salva.pdf" in names


async def test_save_to_cloud_respeita_quota(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(quota.PLAN_QUOTA_GB, AccountPlan.ESSENCIAL, 0)

    user = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(user)
    template_id = await _create_template(client, headers)

    lawsuit_type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    lawsuit = await _create_lawsuit(
        client,
        headers,
        user_id=str(user.user_id),
        lawsuit_type_id=lawsuit_type_id,
        stage_id=stage_id,
    )

    response = await client.post(
        f"/api/v1/templates/{template_id}/save-to-cloud",
        json={"lawsuit_id": str(lawsuit["id"])},
        headers=headers,
    )
    assert response.status_code == 422
    assert "quota" in response.json()["detail"].lower()


@dataclass
class SentDocument:
    to: str
    subject: str
    body: str
    filename: str
    content: bytes


class FakeDocumentMailer:
    """Dublê de `DocumentMailer` (regra: nunca SMTP real em teste) — grava o envio ou
    simula canal não configurado."""

    def __init__(self, *, configured: bool = True) -> None:
        self.sent: list[SentDocument] = []
        self._configured = configured

    async def send(
        self, *, to: str, subject: str, body: str, filename: str, content: bytes
    ) -> None:
        if not self._configured:
            raise ChannelNotConfiguredError("SMTP_HOST não configurado.")
        self.sent.append(
            SentDocument(to=to, subject=subject, body=body, filename=filename, content=content)
        )


async def _create_template_row(
    session_factory: SessionFactory, tenant_id: uuid.UUID, user_id: uuid.UUID, name: str
) -> uuid.UUID:
    async with session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        template = Template(
            tenant_id=tenant_id,
            name=name,
            type=TemplateType.CONTRATO,
            content="<p>Corpo</p>",
            created_by=user_id,
        )
        session.add(template)
        await session.flush()
        return template.id


async def test_envio_de_email_anexa_o_pdf_com_o_nome_do_modelo(
    app_session_factory: SessionFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.GESTOR)
    template_id = await _create_template_row(
        app_session_factory, user.tenant_id, user.user_id, "Procuração"
    )
    mailer = FakeDocumentMailer()

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        service = TemplateGenerationService(
            session, user.tenant_id, storage=create_file_storage(), mailer=mailer
        )
        current_user = await session.get(User, user.user_id)
        assert current_user is not None
        await service.send_email(
            template_id,
            customer_id=None,
            lawsuit_id=None,
            to="cliente@example.com",
            subject=None,
            current_user=current_user,
        )

    assert len(mailer.sent) == 1
    assert mailer.sent[0].filename == "Procuração.pdf"
    assert mailer.sent[0].to == "cliente@example.com"
    assert mailer.sent[0].content.startswith(b"%PDF")


async def test_mailer_nao_configurado_levanta_erro_explicito(
    app_session_factory: SessionFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.GESTOR)
    template_id = await _create_template_row(
        app_session_factory, user.tenant_id, user.user_id, "Sem SMTP"
    )
    mailer = FakeDocumentMailer(configured=False)

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        service = TemplateGenerationService(
            session, user.tenant_id, storage=create_file_storage(), mailer=mailer
        )
        current_user = await session.get(User, user.user_id)
        assert current_user is not None
        with pytest.raises(ChannelNotConfiguredError):
            await service.send_email(
                template_id,
                customer_id=None,
                lawsuit_id=None,
                to="cliente@example.com",
                subject=None,
                current_user=current_user,
            )
