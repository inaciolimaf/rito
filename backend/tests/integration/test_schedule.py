"""Spec 037 — agenda: listagem por intervalo, eixo alternável e feed iCal público.

Cobre as regras 1 (só show_in_schedule), 2 (date_field troca o eixo), 5 (feed:
token secreto, UID estável, timezone da conta, janela, só tarefas do usuário,
regenerar invalida) e 8 (máximo de 90 dias por consulta). A validação do iCal é
por parser (`icalendar`), nunca por comparação de string.
"""

from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from icalendar import Calendar
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.account.models import Account
from app.domain.users.models import UserRole
from tests.clock import hoje
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits_listing import LawsuitFactory, _make_factory
from tests.integration.test_posts import _create_task_type

_TODAY = hoje()
_IN = _TODAY + timedelta(days=10)
_OUT = _TODAY + timedelta(days=45)


@pytest.fixture
async def factory(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> LawsuitFactory:
    return await _make_factory(client, make_user, app_session_factory)


async def _setup_post(
    client: AsyncClient,
    factory: LawsuitFactory,
    *,
    user_ids: list[str] | None = None,
    **extra: object,
) -> dict[str, Any]:
    """Processo + tipo + tarefa com show_in_schedule — a forma curta do cenário."""
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, factory.headers, reward=8)
    response = await client.post(
        "/api/v1/posts",
        json={
            "lawsuit_id": lawsuit_id,
            "task_type_id": task_type_id,
            "user_ids": user_ids or [str(factory.gestor.user_id)],
            "scheduled_date": _IN.isoformat(),
            "show_in_schedule": True,
            **extra,
        },
        headers=factory.headers,
    )
    assert response.status_code == 201, response.json()
    return dict(response.json())


async def _schedule_ids(
    client: AsyncClient,
    headers: dict[str, str],
    from_: date,
    to: date,
    **params: object,
) -> set[str]:
    query = f"from={from_.isoformat()}&to={to.isoformat()}"
    for key, value in params.items():
        query += f"&{key}={value}"
    response = await client.get(f"/api/v1/schedule?{query}", headers=headers)
    assert response.status_code == 200, response.json()
    return {str(item["post_id"]) for item in response.json()["items"]}


async def _enable_feed(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post("/api/v1/schedule/ical/enable", headers=headers)
    assert response.status_code == 200, response.json()
    return str(response.json()["url"])


def _parse_feed(content: bytes) -> Calendar:
    calendar = Calendar.from_ical(content)
    assert calendar is not None
    return calendar


def _feed_uids(calendar: Calendar) -> list[str]:
    return [str(event["UID"]) for event in calendar.walk("VEVENT")]


# ─── Listagem (regras 1, 2 e 8) ───────────────────────────────────────────────


async def test_intervalo_retorna_so_o_que_cai_nele(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    # A visão (mês/semana/dia) é decisão do front; o contrato é o intervalo — aqui
    # três recortes (mês, semana, dia) sobre o mesmo par de tarefas dentro/fora.
    dentro = await _setup_post(client, factory)
    fora = await _setup_post(client, factory, scheduled_date=_OUT.isoformat())

    mes = await _schedule_ids(client, factory.headers, _TODAY, _TODAY + timedelta(days=30))
    assert str(dentro["id"]) in mes
    assert str(fora["id"]) not in mes

    semana = await _schedule_ids(client, factory.headers, _TODAY, _TODAY + timedelta(days=6))
    assert str(dentro["id"]) not in semana

    dia = await _schedule_ids(client, factory.headers, _IN, _IN)
    assert str(dentro["id"]) in dia


async def test_date_field_troca_o_eixo(client: AsyncClient, factory: LawsuitFactory) -> None:
    # Compromisso em _IN, prazo fatal em _OUT: cada eixo enxerga a tarefa num
    # intervalo diferente (regra 2).
    post = await _setup_post(client, factory, deadline_date=_OUT.isoformat())

    janela_compromisso = await _schedule_ids(client, factory.headers, _IN, _IN)
    assert str(post["id"]) in janela_compromisso

    janela_compromisso_no_eixo_prazo = await _schedule_ids(
        client, factory.headers, _IN, _IN, date_field="deadline"
    )
    assert str(post["id"]) not in janela_compromisso_no_eixo_prazo

    janela_prazo_no_eixo_prazo = await _schedule_ids(
        client, factory.headers, _OUT, _OUT, date_field="deadline"
    )
    assert str(post["id"]) in janela_prazo_no_eixo_prazo


async def test_so_tarefas_com_show_in_schedule(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    visivel = await _setup_post(client, factory)
    oculta = await _setup_post(client, factory, show_in_schedule=False)

    ids = await _schedule_ids(client, factory.headers, _TODAY, _TODAY + timedelta(days=30))
    assert str(visivel["id"]) in ids
    assert str(oculta["id"]) not in ids


async def test_intervalo_acima_de_90_dias_da_422(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    response = await client.get(
        f"/api/v1/schedule?from={_TODAY.isoformat()}"
        f"&to={(_TODAY + timedelta(days=91)).isoformat()}",
        headers=factory.headers,
    )
    assert response.status_code == 422


# ─── Feed iCal (regra 5) ──────────────────────────────────────────────────────


async def test_feed_e_rfc5545_valido(client: AsyncClient, factory: LawsuitFactory) -> None:
    await _setup_post(client, factory, scheduled_time="14:30:00", location="Fórum Central")
    await _setup_post(client, factory, all_day=True, scheduled_time=None)
    url = await _enable_feed(client, factory.headers)

    response = await client.get(url)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")

    calendar = _parse_feed(response.content)
    assert str(calendar["VERSION"]) == "2.0"
    # Cabeçalhos de refresh (regra 5): Google Agenda respeita os dois.
    assert str(calendar["X-PUBLISHED-TTL"]) == "PT1H"
    assert calendar.get("REFRESH-INTERVAL") is not None
    events = calendar.walk("VEVENT")
    assert len(events) == 2
    for event in events:
        assert event.get("UID") is not None
        assert event.get("DTSTART") is not None


async def test_uid_estavel_entre_duas_geracoes(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    await _setup_post(client, factory)
    url = await _enable_feed(client, factory.headers)

    primeira = _parse_feed((await client.get(url)).content)
    segunda = _parse_feed((await client.get(url)).content)
    assert _feed_uids(primeira) == _feed_uids(segunda)


async def test_token_invalido_da_404(client: AsyncClient, factory: LawsuitFactory) -> None:
    response = await client.get("/ical/token-que-nao-existe.ics")
    assert response.status_code == 404


async def test_regenerar_invalida_token_anterior(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    await _setup_post(client, factory)
    antiga = await _enable_feed(client, factory.headers)
    assert (await client.get(antiga)).status_code == 200

    response = await client.post("/api/v1/schedule/ical/regenerate", headers=factory.headers)
    assert response.status_code == 200
    nova = str(response.json()["url"])
    assert nova != antiga

    assert (await client.get(antiga)).status_code == 404
    assert (await client.get(nova)).status_code == 200


async def test_feed_nao_vaza_tarefa_de_outro_usuario(
    client: AsyncClient,
    factory: LawsuitFactory,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    outro = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    do_gestor = await _setup_post(client, factory)
    do_outro = await _setup_post(client, factory, user_ids=[str(outro.user_id)])

    url = await _enable_feed(client, factory.headers)
    calendar = _parse_feed((await client.get(url)).content)
    uids = _feed_uids(calendar)
    assert f"{do_gestor['id']}@rito.local" in uids
    assert f"{do_outro['id']}@rito.local" not in uids


async def test_feed_respeita_timezone_da_conta(
    client: AsyncClient,
    factory: LawsuitFactory,
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Conta em America/Manaus (UTC-4, sem horário de verão): 09:00 local vira 13:00Z.
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, factory.gestor.tenant_id)
        session.add(
            Account(
                tenant_id=factory.gestor.tenant_id,
                name="Escritório",
                alternate_name="Escritório",
                identification="00000000000100",
                state="AM",
                city="Manaus",
                postal_code="69000000",
                street="Rua",
                region="Centro",
                cellphone="92999999999",
                phone="9233333333",
                email="contato@example.com",
                email_admin="admin@example.com",
                timezone="America/Manaus",
            )
        )
    await _setup_post(client, factory, scheduled_time="09:00:00")
    url = await _enable_feed(client, factory.headers)

    calendar = _parse_feed((await client.get(url)).content)
    (event,) = calendar.walk("VEVENT")
    dtstart = event.decoded("DTSTART")
    assert dtstart.hour == 13
    assert dtstart.minute == 0
    assert str(dtstart.tzinfo) == "UTC"


async def test_feed_so_traz_tarefas_com_show_in_schedule(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    visivel = await _setup_post(client, factory)
    await _setup_post(client, factory, show_in_schedule=False)
    url = await _enable_feed(client, factory.headers)

    calendar = _parse_feed((await client.get(url)).content)
    assert _feed_uids(calendar) == [f"{visivel['id']}@rito.local"]
