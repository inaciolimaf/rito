"""Webhooks outbound (spec 093 §8).

Nenhuma chamada de rede: o `WebhookSender` é Protocol, e o teste passa uma implementação
que devolve o que o caso precisa — 500, 400, timeout, redirect. É o que permite exercitar
o backoff de 1/5/15 minutos sem esperar 21 minutos.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.integration_alerts.models import IntegrationAlert
from app.domain.users.models import UserRole
from app.domain.webhooks.models import WebhookDelivery, WebhookEndpoint
from app.domain.webhooks.sender import SendResult
from app.domain.webhooks.service import MAX_FAILURE_STREAK, WebhookService
from app.domain.webhooks.signature import SIGNATURE_HEADER, TIMESTAMP_HEADER, verify
from tests.integration.conftest import SeededUser, auth_header
from tests.integration.test_lawsuits import (
    _auth_header,
    _create_customer,
    _create_lawsuit,
    _create_lawsuit_type,
    _create_stage,
)
from tests.integration.test_posts import _create_post, _create_task_type

pytestmark = pytest.mark.asyncio

URL = "https://8.8.8.8/hooks/rito"


class FakeSender:
    """Implementação de `WebhookSender` (LSP): responde o roteiro e guarda o que recebeu."""

    def __init__(self, *results: SendResult) -> None:
        self.results = list(results) or [SendResult(status_code=200, body="ok", duration_ms=5)]
        self.calls: list[dict[str, Any]] = []

    async def send(
        self, *, url: str, body: bytes, headers: dict[str, str], allow_local: bool
    ) -> SendResult:
        self.calls.append({"url": url, "body": body, "headers": headers})
        return self.results.pop(0) if len(self.results) > 1 else self.results[0]


def _use(sender: object) -> None:
    from app.domain.webhooks.router import get_webhook_sender
    from app.main import app

    app.dependency_overrides[get_webhook_sender] = lambda: sender


@pytest.fixture(autouse=True)
def _clear_overrides() -> Any:
    from app.domain.webhooks.router import get_webhook_sender
    from app.main import app

    yield
    app.dependency_overrides.pop(get_webhook_sender, None)


async def _criar_endpoint(
    client: AsyncClient, user: SeededUser, *, url: str = URL
) -> dict[str, Any]:
    resposta = await client.post(
        "/api/v1/webhook-endpoints",
        json={"name": f"n8n {uuid.uuid4().hex[:6]}", "url": url, "headers": {}},
        headers=auth_header(user),
    )
    assert resposta.status_code == 201, resposta.text
    return dict(resposta.json())


async def _service(
    sessions: async_sessionmaker[AsyncSession],
    user: SeededUser,
    sender: FakeSender,
    *,
    now: datetime | None = None,
) -> Any:
    """Um contexto de sessão com o service montado — usado nos casos que não passam
    pela API (retry do worker, sequência de falhas)."""
    session = sessions()
    return session, WebhookService(session, user.tenant_id, sender=sender, now=now)


async def _deliveries(
    sessions: async_sessionmaker[AsyncSession], user: SeededUser
) -> list[WebhookDelivery]:
    async with sessions() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        stmt = select(WebhookDelivery).order_by(WebhookDelivery.created_at)
        return list((await session.scalars(stmt)).all())


# ------------------------------------------------------------------- payloads


async def test_payload_de_task_completed_bate_com_o_contrato(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """O contrato é público: o n8n do escritório lê estas chaves, e renomear uma quebra
    a integração de quem já ligou os fios."""
    user = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(user)
    type_id, _grupo = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    customer_id = await _create_customer(client, headers, "Cliente do Webhook")
    lawsuit = await _create_lawsuit(
        client,
        headers,
        user_id=str(user.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        parties=[{"customer_id": customer_id, "pole": "ATIVO", "is_client": True}],
    )
    task_type_id = await _create_task_type(client, headers)
    post = await _create_post(
        client,
        headers,
        lawsuit_id=str(lawsuit["id"]),
        task_type_id=task_type_id,
        user_ids=[str(user.user_id)],
    )

    sender = FakeSender()
    _use(sender)
    endpoint = await _criar_endpoint(client, user)
    resposta = await client.post(
        f"/api/v1/webhook-endpoints/{endpoint['id']}/test",
        json={"event": "task.completed", "payload": {"post_id": str(post["id"])}},
        headers=auth_header(user),
    )

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()["payload"]
    assert corpo["event"] == "task.completed"
    assert set(corpo) >= {"event", "occurred_at", "tenant_id", "task", "lawsuit", "users"}
    assert set(corpo["task"]) == {
        "id",
        "title",
        "notes",
        "location",
        "scheduled_date",
        "deadline_date",
        "completed_at",
        "points",
    }
    assert set(corpo["lawsuit"]) == {
        "id",
        "process_number",
        "protocol_number",
        "notes",
        "stage",
        "responsible_id",
        "customers",
    }
    assert corpo["lawsuit"]["customers"][0]["name"] == "Cliente do Webhook"
    assert corpo["users"][0]["id"] == str(user.user_id)


async def test_payload_de_stage_changed_bate_com_o_contrato(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(user)
    type_id, _grupo = await _create_lawsuit_type(client, headers)
    origem = await _create_stage(client, headers)
    destino = await _create_stage(client, headers)
    customer_id = await _create_customer(client, headers, "Cliente da Etapa")
    lawsuit = await _create_lawsuit(
        client,
        headers,
        user_id=str(user.user_id),
        lawsuit_type_id=type_id,
        stage_id=origem,
        parties=[{"customer_id": customer_id, "pole": "ATIVO", "is_client": True}],
    )

    _use(FakeSender())
    endpoint = await _criar_endpoint(client, user)
    resposta = await client.post(
        f"/api/v1/webhook-endpoints/{endpoint['id']}/test",
        json={
            "event": "lawsuit.stage_changed",
            "payload": {
                "lawsuit_id": str(lawsuit["id"]),
                "from_stage_id": origem,
                "stage_id": destino,
                "changed_by": str(user.user_id),
            },
        },
        headers=auth_header(user),
    )

    corpo = resposta.json()["payload"]
    assert corpo["event"] == "lawsuit.stage_changed"
    assert corpo["lawsuit"]["from_stage"] and corpo["lawsuit"]["to_stage"]
    assert corpo["changed_by"]["id"] == str(user.user_id)


async def test_assinatura_vai_no_header_e_fecha_com_o_segredo(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 2 ponta a ponta: o que o cliente recebe é verificável com o segredo que
    ele guardou no cadastro."""
    user = await make_user(role=UserRole.GESTOR)
    sender = FakeSender()
    _use(sender)
    endpoint = await _criar_endpoint(client, user)
    segredo = endpoint["secret"]

    await client.post(
        f"/api/v1/webhook-endpoints/{endpoint['id']}/test",
        json={"event": "task.completed", "payload": {}},
        headers=auth_header(user),
    )

    enviado = sender.calls[0]
    assert verify(
        secret=segredo,
        body=enviado["body"],
        timestamp=int(enviado["headers"][TIMESTAMP_HEADER]),
        signature=enviado["headers"][SIGNATURE_HEADER],
    )


# --------------------------------------------------------------------- retry


async def test_erro_500_agenda_nova_tentativa_com_backoff(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 3: 1, 5 e 15 minutos. Não é retry dentro da request — segurar o usuário
    por 21 minutos seria absurdo."""
    user = await make_user(role=UserRole.GESTOR)
    _use(FakeSender(SendResult(status_code=500, body="boom", duration_ms=7)))
    endpoint = await _criar_endpoint(client, user)

    resposta = await client.post(
        f"/api/v1/webhook-endpoints/{endpoint['id']}/test",
        json={"event": "task.completed", "payload": {}},
        headers=auth_header(user),
    )

    corpo = resposta.json()
    assert corpo["status_code"] == 500
    assert corpo["delivered_at"] is None
    assert corpo["next_attempt_at"] is not None
    agendada = datetime.fromisoformat(corpo["next_attempt_at"])
    assert timedelta(seconds=30) < agendada - datetime.now(UTC) <= timedelta(minutes=1)


async def test_erro_400_nao_e_retentado(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 3: retentar um 401 três vezes só produz três 401 — é configuração errada,
    não instabilidade."""
    user = await make_user(role=UserRole.GESTOR)
    _use(FakeSender(SendResult(status_code=400, body="payload inválido", duration_ms=4)))
    endpoint = await _criar_endpoint(client, user)

    corpo = (
        await client.post(
            f"/api/v1/webhook-endpoints/{endpoint['id']}/test",
            json={"event": "task.completed", "payload": {}},
            headers=auth_header(user),
        )
    ).json()

    assert corpo["status_code"] == 400
    assert corpo["next_attempt_at"] is None


async def test_timeout_conta_como_falha_e_retenta(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.GESTOR)
    _use(
        FakeSender(
            SendResult(status_code=None, body="", duration_ms=10_000, error="Sem resposta em 10s.")
        )
    )
    endpoint = await _criar_endpoint(client, user)

    corpo = (
        await client.post(
            f"/api/v1/webhook-endpoints/{endpoint['id']}/test",
            json={"event": "task.completed", "payload": {}},
            headers=auth_header(user),
        )
    ).json()

    assert corpo["status_code"] is None
    assert "Sem resposta" in corpo["error"]
    assert corpo["next_attempt_at"] is not None


async def test_worker_retenta_o_que_venceu_e_para_na_terceira(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 3: são 3 tentativas de retry além da primeira; depois disso a entrega fica
    parada esperando decisão humana, não tentando para sempre."""
    user = await make_user(role=UserRole.GESTOR)
    falha = SendResult(status_code=503, body="fora do ar", duration_ms=9)
    sender = FakeSender(falha)
    _use(sender)
    endpoint = await _criar_endpoint(client, user)
    await client.post(
        f"/api/v1/webhook-endpoints/{endpoint['id']}/test",
        json={"event": "task.completed", "payload": {}},
        headers=auth_header(user),
    )

    # O relógio avança a cada volta: o backoff empurra a próxima tentativa para frente,
    # e um "agora" fixo só encontraria a primeira delas vencida.
    for tentativa in range(1, 5):
        async with app_session_factory() as session, session.begin():
            await set_tenant_context(session, user.tenant_id)
            service = WebhookService(
                session,
                user.tenant_id,
                sender=sender,
                now=datetime.now(UTC) + timedelta(hours=tentativa),
            )
            await service.retry_due()

    entregas = await _deliveries(app_session_factory, user)
    assert len(entregas) == 1, "retry não cria linha nova — é a mesma entrega"
    assert entregas[0].attempt == 4
    assert entregas[0].next_attempt_at is None, "a quarta tentativa é a última"


# ----------------------------------------------------------------------- SSRF


async def test_url_http_externa_e_rejeitada(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.GESTOR)
    _use(FakeSender())

    resposta = await client.post(
        "/api/v1/webhook-endpoints",
        json={"name": "Inseguro", "url": "http://8.8.8.8/hook", "headers": {}},
        headers=auth_header(user),
    )

    assert resposta.status_code == 422
    assert "HTTPS" in resposta.json()["detail"]


async def test_ip_privado_e_bloqueado(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """O vetor clássico: a URL é escolhida pelo usuário e o servidor está na rede
    interna. Bloquear só na string não bastaria — a validação é na resolução."""
    user = await make_user(role=UserRole.GESTOR)
    _use(FakeSender())

    resposta = await client.post(
        "/api/v1/webhook-endpoints",
        json={"name": "Interno", "url": "https://10.0.0.5/hook", "headers": {}},
        headers=auth_header(user),
    )

    assert resposta.status_code == 422
    assert "rede interna" in resposta.json()["detail"]


async def test_redirecionamento_para_host_privado_e_bloqueado() -> None:
    """Regra 7, o caso mais sutil: o destino é público, e o `Location` que ele devolve
    aponta para dentro. Seguir redirect cegamente desfaria toda a validação da URL."""
    import httpx

    from app.domain.webhooks.sender import HttpxWebhookSender

    def responder(request: httpx.Request) -> httpx.Response:
        if request.url.host == "8.8.8.8":
            return httpx.Response(302, headers={"location": "https://169.254.169.254/creds"})
        raise AssertionError("o redirecionamento para host privado não pode ter sido seguido")

    sender = HttpxWebhookSender()
    transport = httpx.MockTransport(responder)
    original = httpx.AsyncClient

    class ClientComMock(original):  # type: ignore[misc, valid-type]
        def __init__(self, **kwargs: Any) -> None:
            kwargs["transport"] = transport
            super().__init__(**kwargs)

    httpx.AsyncClient = ClientComMock  # type: ignore[misc]
    try:
        resultado = await sender.send(url=URL, body=b"{}", headers={}, allow_local=False)
    finally:
        httpx.AsyncClient = original  # type: ignore[misc]

    assert resultado.status_code is None
    assert "Redirecionamento bloqueado" in (resultado.error or "")


# ------------------------------------------------------------ desativação e log


async def test_vinte_falhas_seguidas_desativam_e_alertam(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 10: destino morto para de ser tentado — e desativar em silêncio trocaria
    um problema visível por um invisível."""
    user = await make_user(role=UserRole.GESTOR)
    sender = FakeSender(SendResult(status_code=500, body="boom", duration_ms=3))
    _use(sender)
    endpoint = await _criar_endpoint(client, user)

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        service = WebhookService(session, user.tenant_id, sender=sender)
        alvo = await session.get(WebhookEndpoint, uuid.UUID(endpoint["id"]))
        assert alvo is not None
        for _falha in range(MAX_FAILURE_STREAK):
            await service.dispatch(alvo, event="task.completed", trigger_payload={})

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        alvo = await session.get(WebhookEndpoint, uuid.UUID(endpoint["id"]))
        assert alvo is not None
        assert alvo.is_active is False
        assert alvo.disabled_at is not None
        alertas = list(
            (
                await session.scalars(
                    select(IntegrationAlert).where(IntegrationAlert.integration == "webhooks")
                )
            ).all()
        )
    assert len(alertas) == 1
    assert "desativado" in alertas[0].message


async def test_entrega_boa_zera_a_sequencia_de_falhas(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Vinte falhas SEGUIDAS. Espalhadas ao longo de um ano são internet ruim, e
    desativar por isso seria pior que o problema."""
    user = await make_user(role=UserRole.GESTOR)
    sender = FakeSender(
        SendResult(status_code=500, body="boom", duration_ms=3),
        SendResult(status_code=200, body="ok", duration_ms=3),
    )
    _use(sender)
    endpoint = await _criar_endpoint(client, user)

    for _vez in range(2):
        await client.post(
            f"/api/v1/webhook-endpoints/{endpoint['id']}/test",
            json={"event": "task.completed", "payload": {}},
            headers=auth_header(user),
        )

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        alvo = await session.get(WebhookEndpoint, uuid.UUID(endpoint["id"]))
        assert alvo is not None
        assert alvo.failure_streak == 0
        assert alvo.is_active is True


async def test_reenvio_usa_o_payload_original(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 11: remontar a partir do estado atual transformaria 'reenviar' em 'mandar
    outra coisa', e é isso que quebra a conciliação do outro lado."""
    user = await make_user(role=UserRole.GESTOR)
    sender = FakeSender(
        SendResult(status_code=500, body="boom", duration_ms=3),
        SendResult(status_code=200, body="ok", duration_ms=3),
    )
    _use(sender)
    endpoint = await _criar_endpoint(client, user)
    primeira = (
        await client.post(
            f"/api/v1/webhook-endpoints/{endpoint['id']}/test",
            json={"event": "task.completed", "payload": {"marcador": "original"}},
            headers=auth_header(user),
        )
    ).json()

    reenvio = await client.post(
        f"/api/v1/webhook-deliveries/{primeira['id']}/retry", headers=auth_header(user)
    )

    assert reenvio.status_code == 200, reenvio.text
    assert reenvio.json()["payload"] == primeira["payload"]
    assert reenvio.json()["delivered_at"] is not None


async def test_resposta_e_truncada_em_dez_kb(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 5: o corpo é diagnóstico, não arquivo — um HTML de 2 MB por entrega
    encheria a tabela sem ajudar ninguém."""
    user = await make_user(role=UserRole.GESTOR)
    _use(FakeSender(SendResult(status_code=500, body="x" * 50_000, duration_ms=3)))
    endpoint = await _criar_endpoint(client, user)

    corpo = (
        await client.post(
            f"/api/v1/webhook-endpoints/{endpoint['id']}/test",
            json={"event": "task.completed", "payload": {}},
            headers=auth_header(user),
        )
    ).json()

    assert len(corpo["response_body"]) == 10 * 1024


async def test_segredo_so_aparece_na_criacao_e_na_rotacao(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 8: exibido uma vez. Listagem que devolve segredo é segredo que vaza em
    log de proxy, em print de tela e em cache de navegador."""
    user = await make_user(role=UserRole.GESTOR)
    _use(FakeSender())
    endpoint = await _criar_endpoint(client, user)
    assert endpoint["secret"]

    listagem = await client.get("/api/v1/webhook-endpoints", headers=auth_header(user))
    assert listagem.json()["items"][0]["secret"] is None

    rotacao = await client.post(
        f"/api/v1/webhook-endpoints/{endpoint['id']}/rotate-secret", headers=auth_header(user)
    )
    assert rotacao.json()["secret"] != endpoint["secret"]


async def test_webhook_de_outro_escritorio_nao_existe(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    dono = await make_user(role=UserRole.GESTOR)
    intruso = await make_user(role=UserRole.GESTOR)
    _use(FakeSender())
    endpoint = await _criar_endpoint(client, dono)

    resposta = await client.post(
        f"/api/v1/webhook-endpoints/{endpoint['id']}/rotate-secret",
        headers=auth_header(intruso),
    )

    assert resposta.status_code == 404
