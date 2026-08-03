"""Spec 034 — ciclo de vida das séries de recorrência de tarefas.

Cobre as regras 1 (concluir gera a próxima), 2 (worker de segurança), 6 (limites),
7 (encerrar preserva), 8 (editar afeta só o futuro), 9 (ocorrência independente) e o
isolamento de tenant na tabela nova (CLAUDE.md §4 — obrigatório por tabela).
"""

from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.posts.recurrence_service import RecurrenceService
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import _auth_header
from tests.integration.test_lawsuits_listing import LawsuitFactory, _make_factory
from tests.integration.test_posts import _create_task_type

_ANCHOR = "2026-08-10"  # uma segunda-feira


@pytest.fixture
async def factory(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> LawsuitFactory:
    return await _make_factory(client, make_user, app_session_factory)


async def _create_recurring_post(
    client: AsyncClient,
    factory: LawsuitFactory,
    *,
    scheduled_date: str = _ANCHOR,
    user_ids: list[str] | None = None,
    recurrence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, factory.headers, reward=8)
    payload: dict[str, Any] = {
        "lawsuit_id": lawsuit_id,
        "task_type_id": task_type_id,
        "user_ids": user_ids or [str(factory.gestor.user_id)],
        "scheduled_date": scheduled_date,
    }
    if recurrence is not None:
        payload["recurrence"] = recurrence
    response = await client.post("/api/v1/posts", json=payload, headers=factory.headers)
    assert response.status_code == 201, response.json()
    return dict(response.json())


async def _posts_of_lawsuit(
    client: AsyncClient, factory: LawsuitFactory, post: dict[str, Any]
) -> list[dict[str, Any]]:
    response = await client.get(
        f"/api/v1/lawsuits/{post['lawsuit_id']}/posts", headers=factory.headers
    )
    assert response.status_code == 200
    return [dict(item) for item in response.json()]


async def _complete(client: AsyncClient, factory: LawsuitFactory, post_id: str) -> None:
    response = await client.post(
        f"/api/v1/posts/{post_id}/complete", json={}, headers=factory.headers
    )
    assert response.status_code == 200, response.json()


async def _get_recurrence(
    client: AsyncClient, factory: LawsuitFactory, post_id: str
) -> dict[str, Any]:
    response = await client.get(f"/api/v1/posts/{post_id}/recurrence", headers=factory.headers)
    assert response.status_code == 200, response.json()
    return dict(response.json())


def _by_date(posts: list[dict[str, Any]], scheduled_date: str) -> dict[str, Any]:
    return next(item for item in posts if item["scheduled_date"] == scheduled_date)


async def test_criar_com_recorrencia_cria_serie_e_vincula_template(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    post = await _create_recurring_post(
        client, factory, recurrence={"period": "SEMANAL", "repeat_on": "DIA_EXATO"}
    )
    assert post["recurrence_id"] is not None

    recurrence = await _get_recurrence(client, factory, post["id"])
    assert recurrence["id"] == post["recurrence_id"]
    assert recurrence["template_post_id"] == post["id"]
    assert recurrence["period"] == "SEMANAL"
    # O template É a 1ª ocorrência: conta 1 e ancora a série na data dele.
    assert recurrence["occurrences_created"] == 1
    assert recurrence["last_generated_date"] == _ANCHOR
    assert recurrence["is_active"] is True


async def test_recorrencia_exige_data_do_compromisso(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    # A validação é Pydantic (regra da âncora) — corta antes de qualquer consulta,
    # então UUIDs aleatórios bastam; sem setup de processo/tipo (orçamento de suíte).
    gestor = await make_user(role=UserRole.GESTOR)
    response = await client.post(
        "/api/v1/posts",
        json={
            "lawsuit_id": str(uuid4()),
            "task_type_id": str(uuid4()),
            "user_ids": [str(gestor.user_id)],
            "recurrence": {"period": "SEMANAL"},
        },
        headers=_auth_header(gestor),
    )
    assert response.status_code == 422


async def test_concluir_a_atual_gera_a_proxima_ocorrencia(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    # Regra 1: a próxima ocorrência nasce ao concluir a atual.
    post = await _create_recurring_post(client, factory, recurrence={"period": "SEMANAL"})
    await _complete(client, factory, str(post["id"]))

    posts = await _posts_of_lawsuit(client, factory, post)
    assert len(posts) == 2
    nxt = _by_date(posts, "2026-08-17")
    # Regra 9: a ocorrência é um post independente, com o SEU reward_snapshot…
    assert nxt["id"] != post["id"]
    assert nxt["reward_snapshot"] == 8
    assert nxt["recurrence_id"] == post["recurrence_id"]
    assert [a["id"] for a in nxt["assignees"]] == [str(factory.gestor.user_id)]

    recurrence = await _get_recurrence(client, factory, str(nxt["id"]))
    assert recurrence["occurrences_created"] == 2
    assert recurrence["last_generated_date"] == "2026-08-17"


async def test_conclusao_parcial_nao_gera(
    client: AsyncClient,
    factory: LawsuitFactory,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    # Regra 1 + regra 3 da 033: a tarefa só fecha como um todo quando TODOS concluem
    # — uma conclusão individual não dispara a série.
    outro = await make_user(tenant_id=factory.gestor.tenant_id)
    post = await _create_recurring_post(
        client,
        factory,
        user_ids=[str(factory.gestor.user_id), str(outro.user_id)],
        recurrence={"period": "SEMANAL"},
    )
    await _complete(client, factory, str(post["id"]))
    assert len(await _posts_of_lawsuit(client, factory, post)) == 1

    await client.post(f"/api/v1/posts/{post['id']}/complete", json={}, headers=_auth_header(outro))
    assert len(await _posts_of_lawsuit(client, factory, post)) == 2


async def test_until_date_encerra_a_serie(client: AsyncClient, factory: LawsuitFactory) -> None:
    # Regra 6: a próxima data cairia depois de until_date → a série encerra.
    post = await _create_recurring_post(
        client,
        factory,
        recurrence={"period": "SEMANAL", "until_date": "2026-08-20"},
    )
    await _complete(client, factory, str(post["id"]))  # gera 17/08 (≤ 20/08)
    posts = await _posts_of_lawsuit(client, factory, post)
    await _complete(client, factory, str(_by_date(posts, "2026-08-17")["id"]))

    posts = await _posts_of_lawsuit(client, factory, post)
    assert len(posts) == 2  # 24/08 passaria de 20/08 — não existe
    recurrence = await _get_recurrence(client, factory, str(post["id"]))
    assert recurrence["is_active"] is False
    assert recurrence["occurrences_created"] == 2


async def test_max_occurrences_encerra_a_serie(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    # Regra 6: max_occurrences conta o template — max=2 gera UMA ocorrência a mais.
    post = await _create_recurring_post(
        client,
        factory,
        recurrence={"period": "SEMANAL", "max_occurrences": 2},
    )
    await _complete(client, factory, str(post["id"]))
    posts = await _posts_of_lawsuit(client, factory, post)
    assert len(posts) == 2

    await _complete(client, factory, str(_by_date(posts, "2026-08-17")["id"]))
    posts = await _posts_of_lawsuit(client, factory, post)
    assert len(posts) == 2
    recurrence = await _get_recurrence(client, factory, str(post["id"]))
    assert recurrence["is_active"] is False


async def test_encerrar_a_serie_preserva_o_ja_gerado(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    post = await _create_recurring_post(client, factory, recurrence={"period": "SEMANAL"})
    await _complete(client, factory, str(post["id"]))
    assert len(await _posts_of_lawsuit(client, factory, post)) == 2

    deleted = await client.delete(f"/api/v1/posts/{post['id']}/recurrence", headers=factory.headers)
    assert deleted.status_code == 204

    # Regra 7: as ocorrências já geradas continuam posts independentes…
    posts = await _posts_of_lawsuit(client, factory, post)
    assert len(posts) == 2
    recurrence = await _get_recurrence(client, factory, str(post["id"]))
    assert recurrence["is_active"] is False
    # …e concluir a atual não gera mais nada.
    await _complete(client, factory, str(_by_date(posts, "2026-08-17")["id"]))
    assert len(await _posts_of_lawsuit(client, factory, post)) == 2


async def test_editar_recorrencia_afeta_so_as_ocorrencias_futuras(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    post = await _create_recurring_post(client, factory, recurrence={"period": "SEMANAL"})
    await _complete(client, factory, str(post["id"]))  # gera 17/08 semanal

    # Regra 8: trocar para MENSAL vale daqui para a frente — a ocorrência de 17/08
    # já gerada fica como está.
    updated = await client.put(
        f"/api/v1/posts/{post['id']}/recurrence",
        json={"period": "MENSAL", "repeat_on": "DIA_EXATO"},
        headers=factory.headers,
    )
    assert updated.status_code == 200, updated.json()
    assert updated.json()["occurrences_created"] == 2

    second = _by_date(await _posts_of_lawsuit(client, factory, post), "2026-08-17")
    await _complete(client, factory, str(second["id"]))

    posts = await _posts_of_lawsuit(client, factory, post)
    assert len(posts) == 3
    # MENSAL a partir de 17/08 com âncora no dia 10 → 10/09 (não 17/09).
    _by_date(posts, "2026-09-10")
    # E a ocorrência antiga não foi reescrita.
    assert _by_date(posts, "2026-08-17")["id"] == second["id"]


async def test_worker_gera_atrasada_sem_duplicar(
    client: AsyncClient,
    factory: LawsuitFactory,
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Regra 2: série diária criada há 3 dias e nunca concluída — o worker coloca a
    # série em dia; rodar de novo no mesmo dia não cria nada (guarda de data única).
    start = (date.today() - timedelta(days=3)).isoformat()
    post = await _create_recurring_post(
        client, factory, scheduled_date=start, recurrence={"period": "DIARIA"}
    )

    async def _sweep() -> int:
        async with app_session_factory() as session, session.begin():
            await set_tenant_context(session, factory.gestor.tenant_id)
            service = RecurrenceService(session=session, tenant_id=factory.gestor.tenant_id)
            return await service.sweep_overdue(date.today())

    generated = await _sweep()
    assert generated == 3  # D-2, D-1 e hoje — o template (D-3) já existia
    posts = await _posts_of_lawsuit(client, factory, post)
    assert len(posts) == 4
    dates = [item["scheduled_date"] for item in posts]
    assert len(set(dates)) == 4  # nenhuma data duplicada

    assert await _sweep() == 0  # idempotente: série já está em dia
    assert len(await _posts_of_lawsuit(client, factory, post)) == 4


async def test_preview_retorna_as_5_proximas_datas(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    post = await _create_recurring_post(client, factory, recurrence={"period": "SEMANAL"})
    response = await client.get(
        f"/api/v1/posts/{post['id']}/recurrence/preview?count=5", headers=factory.headers
    )
    assert response.status_code == 200
    assert response.json()["dates"] == [
        "2026-08-17",
        "2026-08-24",
        "2026-08-31",
        "2026-09-07",
        "2026-09-14",
    ]


async def test_tarefa_avulsa_nao_tem_recorrencia(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    post = await _create_recurring_post(client, factory, recurrence=None)
    assert post["recurrence_id"] is None
    response = await client.get(f"/api/v1/posts/{post['id']}/recurrence", headers=factory.headers)
    assert response.status_code == 404


async def test_tenant_b_nao_enxerga_serie_do_tenant_a(
    client: AsyncClient,
    factory: LawsuitFactory,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    post = await _create_recurring_post(client, factory, recurrence={"period": "SEMANAL"})

    # Via API: o post nem existe para o outro tenant (404, não 403).
    intruder = await make_user()
    response = await client.get(
        f"/api/v1/posts/{post['id']}/recurrence", headers=_auth_header(intruder)
    )
    assert response.status_code == 404

    # Direto no banco: RLS filtra post_recurrences pelo app.tenant_id da sessão.
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, intruder.tenant_id)
        rows = await session.execute(
            text("SELECT count(*) FROM post_recurrences WHERE id = CAST(:id AS uuid)"),
            {"id": post["recurrence_id"]},
        )
        assert rows.scalar_one() == 0
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, factory.gestor.tenant_id)
        rows = await session.execute(
            text("SELECT count(*) FROM post_recurrences WHERE id = CAST(:id AS uuid)"),
            {"id": post["recurrence_id"]},
        )
        assert rows.scalar_one() == 1
