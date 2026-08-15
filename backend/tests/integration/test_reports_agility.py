"""Relatórios: Agilidade e Produtividade (spec 071).

A view materializada agility_daily é estática entre refreshes (regra 10, mesmo padrão
do Taskscore/039): os testes concluem tarefas pela API e chamam `refresh_agility_daily`
direto com a MIGRATIONS_DATABASE_URL — a fila nunca participa de teste (CLAUDE.md §3).
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.domain.users.models import UserRole
from app.workers.agility import refresh_agility_daily
from tests.integration.conftest import SeededUser, auth_header
from tests.integration.test_lawsuits_listing import LawsuitFactory, _make_factory
from tests.integration.test_posts import _create_task_type
from tests.integration.test_taskscore import _complete, _setup_post

_NOW = datetime.now(UTC)


def _today_moment() -> datetime:
    """Uma hora atrás, sem cruzar a virada do dia (evita flake perto da meia-noite)."""
    candidate = datetime.now(UTC) - timedelta(hours=1)
    if candidate.date() != datetime.now(UTC).date():
        return datetime.now(UTC)
    return candidate


@pytest.fixture
async def factory(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> LawsuitFactory:
    return await _make_factory(client, make_user, app_session_factory)


async def _refresh() -> None:
    url = get_settings().migrations_database_url
    assert url is not None
    await refresh_agility_daily(url)


async def _agility(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    from_: str | None = None,
    to: str | None = None,
    user_id: str | None = None,
) -> dict[str, object]:
    params: dict[str, str] = {}
    if from_:
        params["from"] = from_
    if to:
        params["to"] = to
    if user_id:
        params["user_id"] = user_id
    response = await client.get("/api/v1/reports/agility", params=params, headers=headers)
    assert response.status_code == 200, response.json()
    return response.json()  # type: ignore[no-any-return]


async def test_em_dia_atraso_e_pendente_com_seed(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    gestor = factory.gestor
    today = _NOW.date()
    tomorrow = (today + timedelta(days=1)).isoformat()
    yesterday = (today - timedelta(days=1)).isoformat()

    on_time_post = await _setup_post(client, factory, [str(gestor.user_id)], deadline_date=tomorrow)
    await _complete(client, factory.headers, on_time_post, at=_today_moment())

    late_post = await _setup_post(client, factory, [str(gestor.user_id)], deadline_date=yesterday)
    await _complete(client, factory.headers, late_post, at=_today_moment())

    await _setup_post(client, factory, [str(gestor.user_id)], deadline_date=tomorrow)
    await _refresh()

    result = await _agility(
        client, factory.headers, from_=yesterday, to=tomorrow, user_id=str(gestor.user_id)
    )
    assert result["on_time"] == 1
    assert result["late"] == 1
    assert result["pending"] == 1


async def test_sem_prazo_fatal_conta_como_em_dia(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    gestor = factory.gestor
    today = _NOW.date().isoformat()
    post_id = await _setup_post(client, factory, [str(gestor.user_id)])
    await _complete(client, factory.headers, post_id, at=_today_moment())
    await _refresh()

    result = await _agility(
        client, factory.headers, from_=today, to=today, user_id=str(gestor.user_id)
    )
    assert result["on_time"] == 1
    assert result["late"] == 0


async def test_medias_de_cumprimento_e_atraso(client: AsyncClient, factory: LawsuitFactory) -> None:
    gestor = factory.gestor
    today = _NOW.date()
    two_days_ago = (today - timedelta(days=2)).isoformat()

    late_post = await _setup_post(
        client, factory, [str(gestor.user_id)], deadline_date=two_days_ago
    )
    await _complete(client, factory.headers, late_post, at=_today_moment())
    await _refresh()

    result = await _agility(
        client,
        factory.headers,
        from_=two_days_ago,
        to=today.isoformat(),
        user_id=str(gestor.user_id),
    )
    assert result["avg_delay_days"] == pytest.approx(2.0, abs=0.1)
    assert result["avg_days_to_complete"] is not None


async def test_privada_agrega_sem_expor_conteudo(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    # Regra 7: tarefa privada entra no agregado (on_time/late), mas some da lista de
    # detalhe "mais atrasados" (spec 033 regra 8: privada é invisível a terceiros).
    gestor = factory.gestor
    today = _NOW.date()
    yesterday = (today - timedelta(days=1)).isoformat()

    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, factory.headers)
    created = await client.post(
        "/api/v1/posts",
        json={
            "lawsuit_id": lawsuit_id,
            "task_type_id": task_type_id,
            "user_ids": [str(gestor.user_id)],
            "scheduled_date": "2026-08-10",
            "deadline_date": yesterday,
            "is_private": True,
        },
        headers=factory.headers,
    )
    assert created.status_code == 201, created.json()
    post_id = str(created.json()["id"])
    await _complete(client, factory.headers, post_id, at=_today_moment())
    await _refresh()

    result = await _agility(
        client,
        factory.headers,
        from_=yesterday,
        to=today.isoformat(),
        user_id=str(gestor.user_id),
    )
    assert result["late"] == 1

    most_delayed = await client.get("/api/v1/reports/most-delayed", headers=factory.headers)
    assert most_delayed.status_code == 200
    assert all(task["post_id"] != post_id for task in most_delayed.json()["tasks"])


async def test_colaborador_ve_so_os_proprios(
    client: AsyncClient, factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    headers = auth_header(colaborador)

    # Regra 8: sem user_id, o Colaborador vê o próprio escopo — não erro.
    own = await _agility(client, headers)
    assert own["on_time"] == 0

    # Pedir o user_id de outra pessoa é 403.
    response = await client.get(
        "/api/v1/reports/agility",
        params={"user_id": str(factory.gestor.user_id)},
        headers=headers,
    )
    assert response.status_code == 403


async def test_periodo_vazio_retorna_zerado(client: AsyncClient, factory: LawsuitFactory) -> None:
    result = await _agility(client, factory.headers, user_id=str(factory.gestor.user_id))
    assert result == {
        "on_time": 0,
        "late": 0,
        "pending": 0,
        "avg_days_to_complete": None,
        "avg_delay_days": None,
        "staleness_hint": result["staleness_hint"],
    }


async def test_prazo_fatal_em_5_dias_corridos(client: AsyncClient, factory: LawsuitFactory) -> None:
    gestor = factory.gestor
    today = _NOW.date()
    within = (today + timedelta(days=4)).isoformat()
    beyond = (today + timedelta(days=10)).isoformat()

    await _setup_post(client, factory, [str(gestor.user_id)], deadline_date=within)
    await _setup_post(client, factory, [str(gestor.user_id)], deadline_date=beyond)

    response = await client.get(
        "/api/v1/reports/productivity",
        params={"user_id": str(gestor.user_id)},
        headers=factory.headers,
    )
    assert response.status_code == 200, response.json()
    assert response.json()["due_in_5_days"] == 1


async def test_grafico_semanal_segunda_a_sexta(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    gestor = factory.gestor
    response = await client.get(
        "/api/v1/reports/productivity/weekly",
        params={"user_id": str(gestor.user_id)},
        headers=factory.headers,
    )
    assert response.status_code == 200, response.json()
    days = response.json()["days"]
    assert len(days) == 5
    assert [d["label"] for d in days] == ["Seg", "Ter", "Qua", "Qui", "Sex"]


async def test_tenant_a_nao_ve_agilidade_de_tenant_b(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    factory_a = await _make_factory(client, make_user, app_session_factory)
    factory_b = await _make_factory(client, make_user, app_session_factory)

    today = _NOW.date().isoformat()
    post_id = await _setup_post(client, factory_a, [str(factory_a.gestor.user_id)])
    await _complete(client, factory_a.headers, post_id, at=_today_moment())
    await _refresh()

    result_b = await _agility(
        client, factory_b.headers, from_=today, to=today, user_id=str(factory_b.gestor.user_id)
    )
    assert result_b["on_time"] == 0

    all_b = await client.get(
        "/api/v1/reports/agility", params={"from": today, "to": today}, headers=factory_b.headers
    )
    assert all_b.status_code == 200
    assert all_b.json()["on_time"] == 0
