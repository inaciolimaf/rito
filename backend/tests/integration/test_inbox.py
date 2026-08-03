"""Spec 036 — caixa de entrada: seções, contadores, preferências e ações em massa.

Cobre as regras 1 (uma seção só), 2 (ordem configurada muda o destino), 3 (privada
de terceiro não aparece), 4 (futura oculta), 5 (concluída sai), 6 (bulk transacional
com 409 + ids), 7 (reassign exige ADMIN), 8 (contadores em 1 query), 9 (preferência
persiste) e 10 (keyset independente por seção).
"""

from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import _auth_header
from tests.integration.test_lawsuits_listing import LawsuitFactory, _make_factory
from tests.integration.test_posts import _create_task_type

_TODAY = date.today()
_NEAR_DEADLINE = (_TODAY + timedelta(days=3)).isoformat()
_FAR_DEADLINE = (_TODAY + timedelta(days=30)).isoformat()
_FUTURE = (_TODAY + timedelta(days=5)).isoformat()


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
    task_type_name: str | None = None,
    **extra: object,
) -> dict[str, Any]:
    lawsuit_id = await factory.create()
    if task_type_name is not None:
        response = await client.post(
            "/api/v1/task-types",
            json={"name": task_type_name, "reward": 0},
            headers=factory.headers,
        )
        assert response.status_code == 201, response.json()
        task_type_id = str(response.json()["id"])
    else:
        task_type_id = await _create_task_type(client, factory.headers, reward=8)
    response = await client.post(
        "/api/v1/posts",
        json={
            "lawsuit_id": lawsuit_id,
            "task_type_id": task_type_id,
            "user_ids": user_ids or [str(factory.gestor.user_id)],
            "scheduled_date": _TODAY.isoformat(),
            **extra,
        },
        headers=factory.headers,
    )
    assert response.status_code == 201, response.json()
    return dict(response.json())


async def _inbox_ids(client: AsyncClient, headers: dict[str, str], section: str) -> set[str]:
    response = await client.get(f"/api/v1/inbox?section={section}", headers=headers)
    assert response.status_code == 200, response.json()
    return {str(item["post_id"]) for item in response.json()["items"]}


async def test_tarefa_aparece_em_uma_secao_so(client: AsyncClient, factory: LawsuitFactory) -> None:
    # Prazo fatal próximo + urgente + não lida: na ordem default, deadline vence (regra 1).
    post = await _setup_post(client, factory, deadline_date=_NEAR_DEADLINE, is_urgent=True)
    sections = ["deadline", "publications", "unread", "urgent", "important", "others"]
    found_in = [
        section
        for section in sections
        if str(post["id"]) in await _inbox_ids(client, factory.headers, section)
    ]
    assert found_in == ["deadline"]


async def test_ordem_configurada_muda_a_secao_de_destino(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    post = await _setup_post(client, factory, deadline_date=_NEAR_DEADLINE, is_urgent=True)

    # Regra 2: com 'urgent' antes de 'deadline', a MESMA tarefa cai em Urgentes.
    response = await client.put(
        "/api/v1/inbox/preferences",
        json={
            "section_order": [
                "urgent",
                "deadline",
                "publications",
                "unread",
                "important",
                "others",
            ],
            "collapsed_sections": ["others"],
        },
        headers=factory.headers,
    )
    assert response.status_code == 200, response.json()
    assert response.json()["section_order"][0] == "urgent"

    assert str(post["id"]) in await _inbox_ids(client, factory.headers, "urgent")
    assert str(post["id"]) not in await _inbox_ids(client, factory.headers, "deadline")

    # Regra 9: a preferência persiste por usuário.
    persisted = await client.get("/api/v1/inbox/preferences", headers=factory.headers)
    assert persisted.json()["section_order"][0] == "urgent"
    assert persisted.json()["collapsed_sections"] == ["others"]

    # Ordem inválida (não é permutação das 6) → 422.
    invalid = await client.put(
        "/api/v1/inbox/preferences",
        json={"section_order": ["urgent", "urgent"], "collapsed_sections": []},
        headers=factory.headers,
    )
    assert invalid.status_code == 422


async def test_contadores_em_query_unica_e_definicoes_das_secoes(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    deadline_post = await _setup_post(client, factory, deadline_date=_NEAR_DEADLINE)
    publication = await _setup_post(client, factory, task_type_name="Intimações Judiciais")
    unread_only = await _setup_post(client, factory)
    # Na ordem default 'unread' precede 'urgent'/'important' (regra 1: primeira seção
    # que casa) — urgente/importante LIDA é que cai na própria seção.
    urgent = await _setup_post(client, factory, is_urgent=True)
    important = await _setup_post(client, factory, is_important=True)
    plain = await _setup_post(client, factory)
    for post in (urgent, important, plain):
        await client.post(f"/api/v1/posts/{post['id']}/read", json={}, headers=factory.headers)

    assert str(deadline_post["id"]) in await _inbox_ids(client, factory.headers, "deadline")
    assert str(publication["id"]) in await _inbox_ids(client, factory.headers, "publications")
    assert str(unread_only["id"]) in await _inbox_ids(client, factory.headers, "unread")
    assert str(urgent["id"]) in await _inbox_ids(client, factory.headers, "urgent")
    assert str(important["id"]) in await _inbox_ids(client, factory.headers, "important")
    assert str(plain["id"]) in await _inbox_ids(client, factory.headers, "others")

    # Regra 8: os contadores batem com o que as seções mostram.
    counts = (await client.get("/api/v1/inbox/counts", headers=factory.headers)).json()
    assert counts == {
        "deadline": 1,
        "publications": 1,
        "unread": 1,
        "urgent": 1,
        "important": 1,
        "others": 1,
    }


async def test_privada_de_terceiro_nao_aparece(
    client: AsyncClient,
    factory: LawsuitFactory,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    outro = await make_user(tenant_id=factory.gestor.tenant_id)
    # Tarefa privada em que SÓ o gestor é responsável: a caixa do colega não a vê (regra 3).
    post = await _setup_post(client, factory, is_private=True)
    assert str(post["id"]) in await _inbox_ids(client, factory.headers, "unread")
    assert str(post["id"]) not in await _inbox_ids(client, _auth_header(outro), "unread")


async def test_futura_oculta_ate_a_data(client: AsyncClient, factory: LawsuitFactory) -> None:
    post = await _setup_post(client, factory, is_future=True, scheduled_date=_FUTURE)
    for section in ("unread", "others", "urgent"):
        assert str(post["id"]) not in await _inbox_ids(client, factory.headers, section)


async def test_concluida_sai_da_caixa(client: AsyncClient, factory: LawsuitFactory) -> None:
    post = await _setup_post(client, factory)
    assert str(post["id"]) in await _inbox_ids(client, factory.headers, "unread")
    await client.post(f"/api/v1/posts/{post['id']}/complete", json={}, headers=factory.headers)
    for section in ("deadline", "unread", "others"):
        assert str(post["id"]) not in await _inbox_ids(client, factory.headers, section)


async def test_acao_em_massa_transacional_e_falha_parcial_409(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    primeiro = await _setup_post(client, factory)
    segundo = await _setup_post(client, factory)

    # Regra 6: um id fora da caixa (não sou responsável) aborta o lote INTEIRO.
    response = await client.post(
        "/api/v1/posts/bulk/complete",
        json={
            "post_ids": [
                str(primeiro["id"]),
                str(segundo["id"]),
                "00000000-0000-0000-0000-000000000000",
            ]
        },
        headers=factory.headers,
    )
    assert response.status_code == 409
    body = response.json()
    # O handler de erros promove chaves extras a membros de extensão do problem+json
    # (mesmo padrão do existing_id da duplicata, spec 032).
    assert body["failed_ids"] == ["00000000-0000-0000-0000-000000000000"]

    # Nada foi concluído — transacional (ou todas, ou nenhuma).
    assert str(primeiro["id"]) in await _inbox_ids(client, factory.headers, "unread")
    assert str(segundo["id"]) in await _inbox_ids(client, factory.headers, "unread")

    # Lote válido: as duas saem da caixa.
    ok = await client.post(
        "/api/v1/posts/bulk/complete",
        json={"post_ids": [str(primeiro["id"]), str(segundo["id"])]},
        headers=factory.headers,
    )
    assert ok.status_code == 200
    for section in ("unread", "others"):
        assert str(primeiro["id"]) not in await _inbox_ids(client, factory.headers, section)

    # bulk/read e bulk/star na linha do próprio usuário.
    terceiro = await _setup_post(client, factory)
    await client.post(
        "/api/v1/posts/bulk/read",
        json={"post_ids": [str(terceiro["id"])]},
        headers=factory.headers,
    )
    assert str(terceiro["id"]) in await _inbox_ids(client, factory.headers, "others")
    await client.post(
        "/api/v1/posts/bulk/star",
        json={"post_ids": [str(terceiro["id"])]},
        headers=factory.headers,
    )
    inbox = await client.get("/api/v1/inbox?section=others", headers=factory.headers)
    assert inbox.json()["items"][0]["is_starred"] is True


async def test_reatribuir_em_massa_exige_administrador(
    client: AsyncClient,
    factory: LawsuitFactory,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    colaborador = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    post = await _setup_post(client, factory)

    # Regra 7: COLABORADOR não reatribui — 403.
    forbidden = await client.post(
        "/api/v1/posts/bulk/reassign",
        json={"post_ids": [str(post["id"])], "to_user_id": str(colaborador.user_id)},
        headers=_auth_header(colaborador),
    )
    assert forbidden.status_code == 403

    # GESTOR reatribui: a tarefa sai da caixa dele e aparece na do colaborador.
    ok = await client.post(
        "/api/v1/posts/bulk/reassign",
        json={"post_ids": [str(post["id"])], "to_user_id": str(colaborador.user_id)},
        headers=factory.headers,
    )
    assert ok.status_code == 200, ok.json()
    assert str(post["id"]) not in await _inbox_ids(client, factory.headers, "unread")
    assert str(post["id"]) in await _inbox_ids(client, _auth_header(colaborador), "unread")


async def test_keyset_independente_por_secao(client: AsyncClient, factory: LawsuitFactory) -> None:
    criados = [await _setup_post(client, factory) for _ in range(3)]

    first_page = await client.get("/api/v1/inbox?section=unread&limit=2", headers=factory.headers)
    assert first_page.status_code == 200
    page = first_page.json()
    assert len(page["items"]) == 2
    assert page["next_cursor"] is not None

    second_page = await client.get(
        f"/api/v1/inbox?section=unread&limit=2&cursor={page['next_cursor']}",
        headers=factory.headers,
    )
    assert len(second_page.json()["items"]) == 1
    assert second_page.json()["next_cursor"] is None

    # Regra 10: a paginação de uma seção não interfere na de outra — e as 3 linhas
    # aparecem exatamente uma vez no percurso completo.
    seen = {item["post_id"] for item in page["items"]} | {
        item["post_id"] for item in second_page.json()["items"]
    }
    assert seen == {str(post["id"]) for post in criados}


async def test_tenant_b_nao_enxerga_preferencias_do_tenant_a(
    client: AsyncClient,
    factory: LawsuitFactory,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await client.put(
        "/api/v1/inbox/preferences",
        json={
            "section_order": [
                "others",
                "urgent",
                "deadline",
                "publications",
                "unread",
                "important",
            ],
            "collapsed_sections": [],
        },
        headers=factory.headers,
    )
    intruder = await make_user()
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, intruder.tenant_id)
        rows = await session.execute(text("SELECT count(*) FROM inbox_preferences"))
        assert rows.scalar_one() == 0
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, factory.gestor.tenant_id)
        rows = await session.execute(text("SELECT count(*) FROM inbox_preferences"))
        assert rows.scalar_one() == 1
