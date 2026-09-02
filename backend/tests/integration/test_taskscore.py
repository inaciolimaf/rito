"""Spec 039 — metas, ranking e painel Taskscore.

A view materializada user_monthly_scores é estática entre refreshes (regra 9): os
testes concluem tarefas pela API e chamam `refresh_user_monthly_scores` direto com a
MIGRATIONS_DATABASE_URL — a fila (Celery) nunca participa de teste (CLAUDE.md §3).
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.domain.users.models import UserRole
from app.workers.scores import refresh_user_monthly_scores
from tests.clock import hoje
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import _auth_header
from tests.integration.test_lawsuits_listing import LawsuitFactory, _make_factory
from tests.integration.test_posts import _create_task_type

_NOW = datetime.now(UTC)


def _this_month() -> str:
    return f"{_NOW:%Y-%m}"


def _last_month() -> str:
    first = _NOW.date().replace(day=1)
    last = first - timedelta(days=1)
    return f"{last:%Y-%m}"


def _now_this_month() -> datetime:
    """Uma hora atrás, sem nunca cruzar a virada de mês (flaky no dia 1 às 00h)."""
    candidate = datetime.now(UTC) - timedelta(hours=1)
    if candidate.month != datetime.now(UTC).month:
        return datetime.now(UTC)
    return candidate


def _last_month_moment() -> datetime:
    first = datetime.now(UTC).date().replace(day=1)
    return datetime.combine(first - timedelta(days=1), datetime.min.time(), tzinfo=UTC) + timedelta(
        hours=12
    )


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
    await refresh_user_monthly_scores(url)


async def _setup_post(
    client: AsyncClient,
    factory: LawsuitFactory,
    assignees: list[str],
    *,
    reward: int = 8,
    deadline_date: str | None = None,
) -> str:
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, factory.headers, reward=reward)
    payload: dict[str, object] = {
        "lawsuit_id": lawsuit_id,
        "task_type_id": task_type_id,
        "user_ids": assignees,
        "scheduled_date": "2026-08-10",
    }
    if deadline_date is not None:
        payload["deadline_date"] = deadline_date
    response = await client.post("/api/v1/posts", json=payload, headers=factory.headers)
    assert response.status_code == 201, response.json()
    return str(response.json()["id"])


async def _complete(
    client: AsyncClient,
    headers: dict[str, str],
    post_id: str,
    *,
    at: datetime | None = None,
    user_id: str | None = None,
) -> None:
    payload: dict[str, str] = {}
    if at is not None:
        payload["completed_at"] = at.isoformat()
    if user_id is not None:
        payload["user_id"] = user_id
    response = await client.post(f"/api/v1/posts/{post_id}/complete", json=payload, headers=headers)
    assert response.status_code == 200, response.json()


async def _me(
    client: AsyncClient, headers: dict[str, str], period: str | None = None
) -> dict[str, object]:
    query = f"?period={period}" if period else ""
    response = await client.get(f"/api/v1/taskscore/me{query}", headers=headers)
    assert response.status_code == 200, response.json()
    return response.json()["summary"]  # type: ignore[no-any-return]


@pytest.mark.commits
async def test_pontos_somam_por_mes(client: AsyncClient, factory: LawsuitFactory) -> None:
    gestor = factory.gestor
    first = await _setup_post(client, factory, [str(gestor.user_id)], reward=8)
    second = await _setup_post(client, factory, [str(gestor.user_id)], reward=12)
    await _complete(client, factory.headers, first, at=_now_this_month())
    await _complete(client, factory.headers, second, at=_now_this_month())
    await _refresh()

    summary = await _me(client, factory.headers)
    assert summary["points"] == 20
    assert summary["tasks_completed"] == 2


@pytest.mark.commits
async def test_retroativa_credita_no_mes_da_data_informada(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    # Regra 2: a competência é a de completed_at, não a do mês corrente.
    gestor = factory.gestor
    post_id = await _setup_post(client, factory, [str(gestor.user_id)], reward=8)
    await _complete(client, factory.headers, post_id, at=_last_month_moment())
    await _refresh()

    assert (await _me(client, factory.headers))["points"] == 0
    assert (await _me(client, factory.headers, period=_last_month()))["points"] == 8


@pytest.mark.commits
async def test_mudar_catalogo_nao_reescreve_historico(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    # Regra 1: points_earned é congelado na conclusão (reward_snapshot da spec 032).
    gestor = factory.gestor
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, factory.headers, reward=8)
    created = await client.post(
        "/api/v1/posts",
        json={
            "lawsuit_id": lawsuit_id,
            "task_type_id": task_type_id,
            "user_ids": [str(gestor.user_id)],
            "scheduled_date": "2026-08-10",
        },
        headers=factory.headers,
    )
    post_id = str(created.json()["id"])
    await _complete(client, factory.headers, post_id, at=_now_this_month())

    updated = await client.put(
        f"/api/v1/task-types/{task_type_id}",
        json={"name": f"Editada {uuid.uuid4().hex[:6]}", "reward": 100},
        headers=factory.headers,
    )
    assert updated.status_code == 200
    await _refresh()

    assert (await _me(client, factory.headers))["points"] == 8


@pytest.mark.commits
async def test_quatro_criterios_de_ordenacao(
    client: AsyncClient, factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    # Seed: gestor (A) 100 pts/2 tarefas; B 30 pts/3 tarefas (1 atrasada, 1 pendente);
    # C 0 pts/1 atribuída. Envolvimento: A=1.0, B=0.75, C=0.0.
    tenant = factory.gestor.tenant_id
    user_b = await make_user(tenant_id=tenant, role=UserRole.COLABORADOR)
    user_c = await make_user(tenant_id=tenant, role=UserRole.COLABORADOR)
    headers_b = _auth_header(user_b)
    a, b, c = (str(factory.gestor.user_id), str(user_b.user_id), str(user_c.user_id))
    tomorrow = (_NOW.date() + timedelta(days=1)).isoformat()
    last_week = (_NOW.date() - timedelta(days=7)).isoformat()

    for _ in range(2):
        post_id = await _setup_post(client, factory, [a], reward=50)
        await _complete(client, factory.headers, post_id, at=_now_this_month())
    for i in range(3):
        post_id = await _setup_post(
            client, factory, [b], reward=10, deadline_date=tomorrow if i < 2 else last_week
        )
        await _complete(client, headers_b, post_id, at=_now_this_month())
    await _setup_post(client, factory, [b])  # pendente — derruba o envolvimento de B
    await _setup_post(client, factory, [c])  # C: atribuída, nunca concluída
    await _refresh()

    async def ranking(sort: str) -> list[str]:
        response = await client.get(
            f"/api/v1/taskscore/ranking?sort={sort}", headers=factory.headers
        )
        assert response.status_code == 200, response.json()
        return [str(item["user_id"]) for item in response.json()["items"]]

    assert await ranking("points") == [a, b, c]
    assert await ranking("volume") == [b, a, c]
    assert (await ranking("late"))[0] == b  # único com atraso; empate em 0 por trás
    assert await ranking("engagement") == [a, b, c]


@pytest.mark.commits
async def test_eltv_soma_todos_os_meses(client: AsyncClient, factory: LawsuitFactory) -> None:
    # Regra 5: ELTV soma desde a criação do usuário — mês passado + mês corrente.
    gestor = factory.gestor
    first = await _setup_post(client, factory, [str(gestor.user_id)], reward=8)
    second = await _setup_post(client, factory, [str(gestor.user_id)], reward=12)
    await _complete(client, factory.headers, first, at=_last_month_moment())
    await _complete(client, factory.headers, second, at=_now_this_month())
    await _refresh()

    summary = await _me(client, factory.headers, period="eltv")
    assert summary["points"] == 20
    assert summary["tasks_completed"] == 2


async def test_sem_meta_mostra_traco(client: AsyncClient, factory: LawsuitFactory) -> None:
    # Regra 3: sem points_goal → goal_pct None (a UI mostra "—"), nunca 0%.
    summary = await _me(client, factory.headers)
    assert summary["points_goal"] is None
    assert summary["goal_pct"] is None


async def test_colaborador_nao_ve_ranking(
    client: AsyncClient, factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    # Regra 6: ranking completo exige ADMINISTRADOR.
    colaborador = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    response = await client.get("/api/v1/taskscore/ranking", headers=_auth_header(colaborador))
    assert response.status_code == 403


@pytest.mark.commits
async def test_sem_prazo_fatal_nao_conta_atraso(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    # Regra 7: sem deadline_date a conclusão não é nem no prazo nem atrasada.
    gestor = factory.gestor
    post_id = await _setup_post(client, factory, [str(gestor.user_id)])
    await _complete(client, factory.headers, post_id, at=_now_this_month())
    await _refresh()

    summary = await _me(client, factory.headers)
    assert summary["tasks_completed"] == 1
    assert summary["on_time"] == 0
    assert summary["late"] == 0


@pytest.mark.commits
async def test_view_e_estatica_ate_o_refresh(client: AsyncClient, factory: LawsuitFactory) -> None:
    # Regra 9: a view é materializada — a conclusão só aparece depois do refresh
    # (em produção: beat de 15 min ou o agendamento imediato do complete).
    gestor = factory.gestor
    post_id = await _setup_post(client, factory, [str(gestor.user_id)], reward=8)
    await _complete(client, factory.headers, post_id, at=_now_this_month())

    assert (await _me(client, factory.headers))["points"] == 0
    await _refresh()
    assert (await _me(client, factory.headers))["points"] == 8


async def test_inativo_some_do_mes_corrente_mas_fica_no_historico(
    client: AsyncClient, factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    # Regra 10.
    marcado = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    post_id = await _setup_post(client, factory, [str(marcado.user_id)], reward=8)
    await _complete(
        client,
        factory.headers,
        post_id,
        at=_last_month_moment(),
        user_id=str(marcado.user_id),
    )
    await _refresh()
    deactivated = await client.post(
        f"/api/v1/users/{marcado.user_id}/deactivate", headers=factory.headers
    )
    assert deactivated.status_code == 204

    async def ids(period: str) -> set[str]:
        response = await client.get(
            f"/api/v1/taskscore/ranking?period={period}", headers=factory.headers
        )
        return {str(item["user_id"]) for item in response.json()["items"]}

    assert str(marcado.user_id) not in await ids(_this_month())
    assert str(marcado.user_id) in await ids("eltv")
    assert str(marcado.user_id) in await ids(_last_month())


@pytest.mark.commits
async def test_tenant_a_nao_vaza_para_tenant_b(
    client: AsyncClient,
    factory: LawsuitFactory,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # A view materializada é global — o isolamento é da view barreira (migration 039).
    post_id = await _setup_post(client, factory, [str(factory.gestor.user_id)], reward=50)
    await _complete(client, factory.headers, post_id, at=_now_this_month())
    await _refresh()

    tenant_b = await _make_factory(client, make_user, app_session_factory)
    assert (await _me(client, tenant_b.headers))["points"] == 0
    response = await client.get("/api/v1/taskscore/ranking", headers=tenant_b.headers)
    assert all(item["points"] == 0 for item in response.json()["items"])
    assert (await _me(client, factory.headers))["points"] == 50


async def test_meta_de_fechamento_alimenta_widget_da_028(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    # Regra 8: a meta por grupo de ação soma no widget de fechamentos dos processos.
    group = await client.post(
        "/api/v1/action-groups",
        json={"name": f"Grupo {uuid.uuid4().hex[:6]}"},
        headers=factory.headers,
    )
    assert group.status_code == 201, group.json()
    saved = await client.put(
        "/api/v1/goals/closures",
        json={"items": [{"action_group_id": group.json()["id"], "monthly_target": 5}]},
        headers=factory.headers,
    )
    assert saved.status_code == 200, saved.json()
    await factory.create("Fechado no mês", closure_date=str(hoje()))

    stats = await client.get("/api/v1/lawsuits/stats", headers=factory.headers)
    goal = stats.json()["closure_goal"]
    assert goal == {"target": 5, "achieved": 1, "pct": 20.0}


@pytest.mark.commits
async def test_meta_de_pontos_por_usuario(
    client: AsyncClient, factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    # PUT /users/{id}/points-goal: GESTOR escreve; o /me passa a refletir o alcance.
    alvo = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    forbidden = await client.put(
        f"/api/v1/users/{alvo.user_id}/points-goal",
        json={"points_goal": 10},
        headers=_auth_header(alvo),
    )
    assert forbidden.status_code == 403

    saved = await client.put(
        f"/api/v1/users/{alvo.user_id}/points-goal",
        json={"points_goal": 10},
        headers=factory.headers,
    )
    assert saved.status_code == 200, saved.json()

    post_id = await _setup_post(client, factory, [str(alvo.user_id)], reward=8)
    await _complete(
        client, factory.headers, post_id, at=_now_this_month(), user_id=str(alvo.user_id)
    )
    await _refresh()

    summary = await _me(client, _auth_header(alvo))
    assert summary["points_goal"] == 10
    assert summary["goal_pct"] == 80.0


@pytest.mark.commits
async def test_grafico_mes_atual_anterior_e_meta(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    gestor = factory.gestor
    first = await _setup_post(client, factory, [str(gestor.user_id)], reward=8)
    second = await _setup_post(client, factory, [str(gestor.user_id)], reward=12)
    await _complete(client, factory.headers, first, at=_last_month_moment())
    await _complete(client, factory.headers, second, at=_now_this_month())
    await client.put(
        f"/api/v1/users/{gestor.user_id}/points-goal",
        json={"points_goal": 50},
        headers=factory.headers,
    )
    await _refresh()

    response = await client.get("/api/v1/taskscore/chart", headers=factory.headers)
    assert response.status_code == 200
    body = response.json()
    assert body["current"] == 12
    assert body["previous"] == 8
    assert body["goal"] == 50

    daily = await client.get("/api/v1/taskscore/chart?granularity=daily", headers=factory.headers)
    assert sum(day["value"] for day in daily.json()["days"]) == 12
