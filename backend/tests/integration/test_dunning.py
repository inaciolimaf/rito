"""Financeiro: inadimplência (spec 061, §8) — atrasados, aging, régua de cobrança,
envio manual, canais sem provider e isolamento por tenant."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.dunning.service import DunningService
from app.integrations.messaging.base import MessagingChannel
from app.integrations.messaging.sms import SmsChannel
from app.integrations.messaging.whatsapp import WhatsAppChannel
from tests.integration.conftest import SeededUser
from tests.integration.test_transactions import _fixtures, _make_gestor_full, _receita_payload

_TODAY = date.today()


@dataclass
class SentMessage:
    to: str
    subject: str
    message: str


class FakeEmailChannel:
    """Dublê de `MessagingChannel` (regra: e-mail sempre mockado em teste) — grava
    cada envio e pode simular falha real por destinatário."""

    def __init__(self, *, fail_for: set[str] | None = None) -> None:
        self.sent: list[SentMessage] = []
        self._fail_for = fail_for or set()

    async def send(self, *, to: str, subject: str, message: str) -> None:
        if to in self._fail_for:
            raise RuntimeError("falha simulada do provider")
        self.sent.append(SentMessage(to=to, subject=subject, message=message))


def _channels(email: FakeEmailChannel | None = None) -> dict[str, MessagingChannel]:
    return {
        "EMAIL": email or FakeEmailChannel(),
        "SMS": SmsChannel(),
        "WHATSAPP": WhatsAppChannel(),
    }


async def _run_daily_rules(
    session_factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    reference_date: date,
    channels: dict[str, MessagingChannel],
) -> int:
    """Worker diário chamado direto, sem fila (CLAUDE.md §3) — mesmo padrão de
    `test_taskscore.py`/`test_resilience_chaos.py` para regras síncronas."""
    async with session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        service = DunningService(session=session, tenant_id=tenant_id, channels=channels)
        return await service.run_daily_rules(reference_date)


async def _create_customer_with_email(
    client: AsyncClient, headers: dict[str, str], *, name: str, email: str | None
) -> str:
    origin = await client.post(
        "/api/v1/customer-origins", json={"name": f"Origem {uuid.uuid4().hex[:8]}"}, headers=headers
    )
    assert origin.status_code == 201
    payload: dict[str, object] = {
        "type": "PF",
        "name": name,
        "origin_id": origin.json()["id"],
    }
    if email is not None:
        payload["email"] = email
    response = await client.post("/api/v1/customers", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    result: str = response.json()["id"]
    return result


async def _create_receita(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    category_id: str,
    cost_center_id: str,
    account_id: str,
    customer_id: str,
    amount: str,
    due_date: date,
) -> str:
    response = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=category_id,
            cost_center_id=cost_center_id,
            account_id=account_id,
            customer_id=customer_id,
            amount=amount,
            due_date=due_date.isoformat(),
        ),
        headers=headers,
    )
    assert response.status_code == 201, response.text
    result: str = response.json()["id"]
    return result


@dataclass
class Setup:
    gestor: SeededUser
    headers: dict[str, str]
    receita_category_id: str
    despesa_category_id: str
    cost_center_id: str
    account_id: str
    customer_id: str
    customer_email: str = field(default="cliente@example.com")


async def _setup(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    *,
    email: str | None = "cliente@example.com",
) -> Setup:
    gestor, headers = await _make_gestor_full(make_user)
    receita_id, despesa_id, cost_center_id, account_id, _b = await _fixtures(client, headers)
    customer_id = await _create_customer_with_email(
        client, headers, name="Cliente Inadimplente", email=email
    )
    return Setup(
        gestor=gestor,
        headers=headers,
        receita_category_id=receita_id,
        despesa_category_id=despesa_id,
        cost_center_id=cost_center_id,
        account_id=account_id,
        customer_id=customer_id,
        customer_email=email or "",
    )


# ---- regra 1: atrasados -----------------------------------------------------------


async def test_atrasados_excluem_interno_pago_e_despesa(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    setup = await _setup(client, make_user)
    overdue_due = _TODAY - timedelta(days=5)

    # atrasado de verdade — entra
    await _create_receita(
        client,
        setup.headers,
        category_id=setup.receita_category_id,
        cost_center_id=setup.cost_center_id,
        account_id=setup.account_id,
        customer_id=setup.customer_id,
        amount="100.00",
        due_date=overdue_due,
    )

    # pago — não entra
    paid = await _create_receita(
        client,
        setup.headers,
        category_id=setup.receita_category_id,
        cost_center_id=setup.cost_center_id,
        account_id=setup.account_id,
        customer_id=setup.customer_id,
        amount="200.00",
        due_date=overdue_due,
    )
    pay = await client.post(
        f"/api/v1/transactions/{paid}/pay",
        json={"payment_date": _TODAY.isoformat()},
        headers=setup.headers,
    )
    assert pay.status_code == 200, pay.text

    # interno — não entra
    internal_response = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=setup.receita_category_id,
            cost_center_id=setup.cost_center_id,
            account_id=setup.account_id,
            customer_id=setup.customer_id,
            amount="300.00",
            due_date=overdue_due.isoformat(),
            is_internal=True,
        ),
        headers=setup.headers,
    )
    assert internal_response.status_code == 201

    # despesa atrasada — não entra (regra 1: só RECEITA)
    despesa_response = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "DESPESA",
            "debit_account_id": setup.account_id,
            "category_id": setup.despesa_category_id,
            "cost_center_id": setup.cost_center_id,
            "amount": "400.00",
            "due_date": overdue_due.isoformat(),
        },
        headers=setup.headers,
    )
    assert despesa_response.status_code == 201

    response = await client.get("/api/v1/transactions/overdue", headers=setup.headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["amount"] == 100.00


# ---- regra 2: faixas de aging -------------------------------------------------------


async def test_faixas_de_aging(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    setup = await _setup(client, make_user)
    cases = {
        "1-15": _TODAY - timedelta(days=10),
        "16-30": _TODAY - timedelta(days=20),
        "31-60": _TODAY - timedelta(days=45),
        "61-90": _TODAY - timedelta(days=75),
        "90+": _TODAY - timedelta(days=120),
    }
    for due in cases.values():
        await _create_receita(
            client,
            setup.headers,
            category_id=setup.receita_category_id,
            cost_center_id=setup.cost_center_id,
            account_id=setup.account_id,
            customer_id=setup.customer_id,
            amount="50.00",
            due_date=due,
        )

    for bucket in cases:
        response = await client.get(
            "/api/v1/transactions/overdue", params={"aging": bucket}, headers=setup.headers
        )
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 1, bucket

    summary = await client.get("/api/v1/transactions/overdue/summary", headers=setup.headers)
    assert summary.status_code == 200, summary.text
    by_aging = {item["bucket"]: item["total"] for item in summary.json()["by_aging"]}
    for bucket in cases:
        assert by_aging[bucket] == 50.00, bucket
    assert summary.json()["total"] == 250.00
    assert summary.json()["top_debtors"][0]["total"] == 250.00


# ---- réguas: disparo, offset negativo, sem duplicar, sem contato, baixa cancela ----


async def test_regua_dispara_no_offset_certo(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    setup = await _setup(client, make_user)
    due = _TODAY - timedelta(days=5)  # atrasado há 5 dias
    tx_id = await _create_receita(
        client,
        setup.headers,
        category_id=setup.receita_category_id,
        cost_center_id=setup.cost_center_id,
        account_id=setup.account_id,
        customer_id=setup.customer_id,
        amount="150.00",
        due_date=due,
    )
    rule = await client.put(
        "/api/v1/dunning-rules",
        json={"days_offset": 5, "channel": "EMAIL", "template": "Olá {{customer_name}}!"},
        headers=setup.headers,
    )
    assert rule.status_code == 200, rule.text

    email_channel = FakeEmailChannel()
    sent = await _run_daily_rules(
        app_session_factory, setup.gestor.tenant_id, _TODAY, _channels(email_channel)
    )

    assert sent == 1
    assert len(email_channel.sent) == 1
    assert email_channel.sent[0].to == setup.customer_email
    assert "Cliente Inadimplente" in email_channel.sent[0].message

    attempts = await client.get(
        f"/api/v1/transactions/{tx_id}/dunning/attempts", headers=setup.headers
    )
    assert attempts.status_code == 200, attempts.text
    items = attempts.json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "SENT"
    assert items[0]["is_manual"] is False


async def test_lembrete_antes_do_vencimento_offset_negativo(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    setup = await _setup(client, make_user)
    due = _TODAY + timedelta(days=3)  # ainda não venceu
    await _create_receita(
        client,
        setup.headers,
        category_id=setup.receita_category_id,
        cost_center_id=setup.cost_center_id,
        account_id=setup.account_id,
        customer_id=setup.customer_id,
        amount="80.00",
        due_date=due,
    )
    rule = await client.put(
        "/api/v1/dunning-rules",
        json={"days_offset": -3, "channel": "EMAIL", "template": "Lembrete!"},
        headers=setup.headers,
    )
    assert rule.status_code == 200, rule.text

    email_channel = FakeEmailChannel()
    sent = await _run_daily_rules(
        app_session_factory, setup.gestor.tenant_id, _TODAY, _channels(email_channel)
    )

    assert sent == 1
    assert len(email_channel.sent) == 1


async def test_mesma_regua_nao_dispara_duas_vezes(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    setup = await _setup(client, make_user)
    due = _TODAY - timedelta(days=5)
    await _create_receita(
        client,
        setup.headers,
        category_id=setup.receita_category_id,
        cost_center_id=setup.cost_center_id,
        account_id=setup.account_id,
        customer_id=setup.customer_id,
        amount="90.00",
        due_date=due,
    )
    await client.put(
        "/api/v1/dunning-rules",
        json={"days_offset": 5, "channel": "EMAIL", "template": "Cobrança"},
        headers=setup.headers,
    )

    email_channel = FakeEmailChannel()
    first = await _run_daily_rules(
        app_session_factory, setup.gestor.tenant_id, _TODAY, _channels(email_channel)
    )
    second = await _run_daily_rules(
        app_session_factory, setup.gestor.tenant_id, _TODAY, _channels(email_channel)
    )

    assert first == 1
    assert second == 0
    assert len(email_channel.sent) == 1


async def test_sem_canal_gera_skipped_com_motivo(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    setup = await _setup(client, make_user, email=None)  # sem e-mail cadastrado
    due = _TODAY - timedelta(days=5)
    tx_id = await _create_receita(
        client,
        setup.headers,
        category_id=setup.receita_category_id,
        cost_center_id=setup.cost_center_id,
        account_id=setup.account_id,
        customer_id=setup.customer_id,
        amount="60.00",
        due_date=due,
    )
    await client.put(
        "/api/v1/dunning-rules",
        json={"days_offset": 5, "channel": "EMAIL", "template": "Cobrança"},
        headers=setup.headers,
    )

    sent = await _run_daily_rules(app_session_factory, setup.gestor.tenant_id, _TODAY, _channels())

    assert sent == 1  # regra 5: tentativa sempre é registrada, silêncio nunca
    attempts = await client.get(
        f"/api/v1/transactions/{tx_id}/dunning/attempts", headers=setup.headers
    )
    items = attempts.json()["items"]
    assert items[0]["status"] == "SKIPPED"
    assert items[0]["error"]


async def test_baixa_cancela_reguas_futuras(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    setup = await _setup(client, make_user)
    due = _TODAY - timedelta(days=5)
    tx_id = await _create_receita(
        client,
        setup.headers,
        category_id=setup.receita_category_id,
        cost_center_id=setup.cost_center_id,
        account_id=setup.account_id,
        customer_id=setup.customer_id,
        amount="70.00",
        due_date=due,
    )
    await client.put(
        "/api/v1/dunning-rules",
        json={"days_offset": 5, "channel": "EMAIL", "template": "Cobrança"},
        headers=setup.headers,
    )
    pay = await client.post(
        f"/api/v1/transactions/{tx_id}/pay",
        json={"payment_date": _TODAY.isoformat()},
        headers=setup.headers,
    )
    assert pay.status_code == 200, pay.text

    email_channel = FakeEmailChannel()
    sent = await _run_daily_rules(
        app_session_factory, setup.gestor.tenant_id, _TODAY, _channels(email_channel)
    )

    assert sent == 0
    assert email_channel.sent == []


async def test_falha_em_um_nao_afeta_os_outros(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    setup = await _setup(client, make_user)
    due = _TODAY - timedelta(days=5)
    await _create_receita(
        client,
        setup.headers,
        category_id=setup.receita_category_id,
        cost_center_id=setup.cost_center_id,
        account_id=setup.account_id,
        customer_id=setup.customer_id,
        amount="10.00",
        due_date=due,
    )
    other_customer = await _create_customer_with_email(
        client, setup.headers, name="Outro Cliente", email="outro@example.com"
    )
    await _create_receita(
        client,
        setup.headers,
        category_id=setup.receita_category_id,
        cost_center_id=setup.cost_center_id,
        account_id=setup.account_id,
        customer_id=other_customer,
        amount="20.00",
        due_date=due,
    )
    await client.put(
        "/api/v1/dunning-rules",
        json={"days_offset": 5, "channel": "EMAIL", "template": "Cobrança"},
        headers=setup.headers,
    )

    email_channel = FakeEmailChannel(fail_for={setup.customer_email})
    sent = await _run_daily_rules(
        app_session_factory, setup.gestor.tenant_id, _TODAY, _channels(email_channel)
    )

    # regra 10: `sent` conta tentativas processadas (SENT + FAILED), não só sucessos —
    # o lançamento que falha vira um DunningAttempt FAILED, e o outro continua sendo
    # processado normalmente (não é uma exceção que para o lote).
    assert sent == 2
    assert len(email_channel.sent) == 1
    assert email_channel.sent[0].to == "outro@example.com"


# ---- envio manual (regra 8) e canal sem provider (regra 9) ------------------------


async def test_envio_manual_sempre_permitido_e_registrado(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    setup = await _setup(client, make_user)
    due = _TODAY - timedelta(days=5)
    tx_id = await _create_receita(
        client,
        setup.headers,
        category_id=setup.receita_category_id,
        cost_center_id=setup.cost_center_id,
        account_id=setup.account_id,
        customer_id=setup.customer_id,
        amount="55.00",
        due_date=due,
    )
    # a régua já rodou pra esse lançamento
    await client.put(
        "/api/v1/dunning-rules",
        json={"days_offset": 5, "channel": "EMAIL", "template": "Cobrança automática"},
        headers=setup.headers,
    )
    await _run_daily_rules(app_session_factory, setup.gestor.tenant_id, _TODAY, _channels())

    # SMS não tem provider real — vira SKIPPED, mas o envio é aceito (regra 9)
    response = await client.post(
        f"/api/v1/transactions/{tx_id}/dunning/send",
        json={"channel": "SMS", "template": "Cobrança manual por SMS"},
        headers=setup.headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_manual"] is True
    assert body["status"] == "SKIPPED"

    attempts = await client.get(
        f"/api/v1/transactions/{tx_id}/dunning/attempts", headers=setup.headers
    )
    items = attempts.json()["items"]
    assert len(items) == 2  # a da régua + a manual — nunca colidem


async def test_canal_sem_provider_vira_skipped_sem_quebrar(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    setup = await _setup(client, make_user)
    due = _TODAY - timedelta(days=5)
    tx_id = await _create_receita(
        client,
        setup.headers,
        category_id=setup.receita_category_id,
        cost_center_id=setup.cost_center_id,
        account_id=setup.account_id,
        customer_id=setup.customer_id,
        amount="45.00",
        due_date=due,
    )
    response = await client.post(
        f"/api/v1/transactions/{tx_id}/dunning/send",
        json={"channel": "WHATSAPP", "template": "Cobrança"},
        headers=setup.headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "SKIPPED"


async def test_envio_manual_exige_receita_em_aberto(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    setup = await _setup(client, make_user)
    tx_id = await _create_receita(
        client,
        setup.headers,
        category_id=setup.receita_category_id,
        cost_center_id=setup.cost_center_id,
        account_id=setup.account_id,
        customer_id=setup.customer_id,
        amount="30.00",
        due_date=_TODAY - timedelta(days=1),
    )
    pay = await client.post(
        f"/api/v1/transactions/{tx_id}/pay",
        json={"payment_date": _TODAY.isoformat()},
        headers=setup.headers,
    )
    assert pay.status_code == 200

    response = await client.post(
        f"/api/v1/transactions/{tx_id}/dunning/send",
        json={"channel": "EMAIL", "template": "Cobrança"},
        headers=setup.headers,
    )
    assert response.status_code == 422


# ---- réguas: CRUD e unicidade -------------------------------------------------------


async def test_regua_upsert_por_offset_e_canal(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    setup = await _setup(client, make_user)
    created = await client.put(
        "/api/v1/dunning-rules",
        json={"days_offset": 10, "channel": "EMAIL", "template": "V1"},
        headers=setup.headers,
    )
    assert created.status_code == 200
    rule_id = created.json()["id"]

    updated = await client.put(
        "/api/v1/dunning-rules",
        json={"days_offset": 10, "channel": "EMAIL", "template": "V2", "is_active": False},
        headers=setup.headers,
    )
    assert updated.status_code == 200
    assert updated.json()["id"] == rule_id  # mesmo registro, não duplicou
    assert updated.json()["template"] == "V2"
    assert updated.json()["is_active"] is False

    listed = await client.get("/api/v1/dunning-rules", headers=setup.headers)
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1


# ---- isolamento por tenant (CLAUDE.md §4) ------------------------------------------


async def test_tenant_a_nao_ve_atrasado_nem_regua_de_tenant_b(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    setup_a = await _setup(client, make_user)
    await _create_receita(
        client,
        setup_a.headers,
        category_id=setup_a.receita_category_id,
        cost_center_id=setup_a.cost_center_id,
        account_id=setup_a.account_id,
        customer_id=setup_a.customer_id,
        amount="99.00",
        due_date=_TODAY - timedelta(days=10),
    )
    await client.put(
        "/api/v1/dunning-rules",
        json={"days_offset": 10, "channel": "EMAIL", "template": "A"},
        headers=setup_a.headers,
    )

    setup_b = await _setup(client, make_user)
    overdue_b = await client.get("/api/v1/transactions/overdue", headers=setup_b.headers)
    assert overdue_b.json()["total"] == 0
    rules_b = await client.get("/api/v1/dunning-rules", headers=setup_b.headers)
    assert rules_b.json()["items"] == []
