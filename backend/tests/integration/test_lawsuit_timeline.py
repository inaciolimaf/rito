import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.lawsuits.models import LawsuitMovement, MovementOrigin
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import (
    _auth_header,
    _create_lawsuit,
    _create_lawsuit_type,
    _create_stage,
)
from tests.perf import e_plumbing

_BASE_TIME = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


async def _setup(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> tuple[SeededUser, dict[str, str], str]:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    lawsuit = await _create_lawsuit(
        client,
        headers,
        user_id=str(gestor.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
    )
    return gestor, headers, str(lawsuit["id"])


async def _add_manual(
    client: AsyncClient,
    headers: dict[str, str],
    lawsuit_id: str,
    title: str,
    occurred_at: datetime,
    body: str | None = None,
) -> dict[str, object]:
    response = await client.post(
        f"/api/v1/lawsuits/{lawsuit_id}/movements",
        json={
            "occurred_at": occurred_at.isoformat(),
            "title": title,
            "body": body,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    result: dict[str, object] = response.json()
    return result


async def _seed_tribunal(
    app_session_factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    lawsuit_id: str,
    title: str,
    occurred_at: datetime,
    external_id: str | None = None,
) -> uuid.UUID:
    """Movimentação TRIBUNAL não tem endpoint (vem da sync DataJud, spec 047) —
    os testes a inserem direto no banco."""
    movement_id = uuid.uuid4()
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        session.add(
            LawsuitMovement(
                id=movement_id,
                tenant_id=tenant_id,
                lawsuit_id=uuid.UUID(lawsuit_id),
                origin=MovementOrigin.TRIBUNAL,
                occurred_at=occurred_at,
                title=title,
                header="TJSP - Tribunal de Justiça de São Paulo",
                external_code=123,
                external_id=external_id,
            )
        )
    return movement_id


async def test_timeline_agrega_fontes_na_ordem_certa(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    gestor, headers, lawsuit_id = await _setup(client, make_user)
    await _seed_tribunal(
        app_session_factory, gestor.tenant_id, lawsuit_id, "Juntada de petição", _BASE_TIME
    )
    await _add_manual(
        client, headers, lawsuit_id, "Ligação para o cliente", _BASE_TIME + timedelta(hours=2)
    )
    await _add_manual(client, headers, lawsuit_id, "Nota interna", _BASE_TIME + timedelta(hours=1))

    response = await client.get(f"/api/v1/lawsuits/{lawsuit_id}/timeline", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    # Regra 1: occurred_at decrescente.
    assert [item["title"] for item in body["items"]] == [
        "Ligação para o cliente",
        "Nota interna",
        "Juntada de petição",
    ]
    assert body["items"][0]["kind"] == "movement_manual"
    assert body["items"][0]["actor"] == "Usuário de Teste"
    assert body["items"][2]["kind"] == "movement_auto"
    assert body["items"][2]["metadata"]["header"] == "TJSP - Tribunal de Justiça de São Paulo"


async def test_toggles_filtram_por_tipo(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    gestor, headers, lawsuit_id = await _setup(client, make_user)
    await _seed_tribunal(app_session_factory, gestor.tenant_id, lawsuit_id, "Juntada", _BASE_TIME)
    await _add_manual(client, headers, lawsuit_id, "Nota manual", _BASE_TIME)

    response = await client.get(
        f"/api/v1/lawsuits/{lawsuit_id}/timeline",
        params={"kinds": "movement_manual"},
        headers=headers,
    )
    items = response.json()["items"]
    assert [item["title"] for item in items] == ["Nota manual"]

    response = await client.get(
        f"/api/v1/lawsuits/{lawsuit_id}/timeline",
        params={"kinds": "movement_auto,movement_manual"},
        headers=headers,
    )
    assert response.json()["total"] == 2


async def test_nenhum_toggle_retorna_vazio(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers, lawsuit_id = await _setup(client, make_user)
    await _add_manual(client, headers, lawsuit_id, "Nota", _BASE_TIME)

    # Regra 2: nenhum tipo marcado (kinds= explícito e vazio) → vazio, não tudo.
    response = await client.get(
        f"/api/v1/lawsuits/{lawsuit_id}/timeline", params={"kinds": ""}, headers=headers
    )
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0

    # Slot sem fonte ainda (task/publication/transaction — specs 032/042/056) → vazio.
    response = await client.get(
        f"/api/v1/lawsuits/{lawsuit_id}/timeline", params={"kinds": "task"}, headers=headers
    )
    assert response.json()["items"] == []


async def test_ordenacao_estavel_com_mesmo_timestamp(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    gestor, headers, lawsuit_id = await _setup(client, make_user)
    await _seed_tribunal(
        app_session_factory, gestor.tenant_id, lawsuit_id, "Auto no mesmo instante", _BASE_TIME
    )
    await _add_manual(client, headers, lawsuit_id, "Manual no mesmo instante", _BASE_TIME)

    response = await client.get(f"/api/v1/lawsuits/{lawsuit_id}/timeline", headers=headers)
    items = response.json()["items"]
    # Regra 1: empate no timestamp desempata por kind (movement_auto < movement_manual).
    assert [item["kind"] for item in items] == ["movement_auto", "movement_manual"]
    # E a ordem é estável entre duas consultas.
    again = await client.get(f"/api/v1/lawsuits/{lawsuit_id}/timeline", headers=headers)
    assert [item["id"] for item in again.json()["items"]] == [item["id"] for item in items]


async def test_paginacao_keyset_nao_repete_nem_pula(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers, lawsuit_id = await _setup(client, make_user)
    for index in range(5):
        await _add_manual(
            client, headers, lawsuit_id, f"Nota {index}", _BASE_TIME + timedelta(hours=index)
        )

    first = await client.get(
        f"/api/v1/lawsuits/{lawsuit_id}/timeline", params={"limit": 2}, headers=headers
    )
    page1 = first.json()
    assert page1["total"] == 5
    assert [item["title"] for item in page1["items"]] == ["Nota 4", "Nota 3"]
    assert page1["next_cursor"] is not None

    seen = [item["id"] for item in page1["items"]]
    cursor = page1["next_cursor"]
    while cursor:
        following = await client.get(
            f"/api/v1/lawsuits/{lawsuit_id}/timeline",
            params={"limit": 2, "cursor": cursor},
            headers=headers,
        )
        page = following.json()
        seen.extend(item["id"] for item in page["items"])
        cursor = page["next_cursor"]

    # 5 itens, nenhum repetido, nenhum pulado; total estável entre páginas.
    assert len(seen) == 5
    assert len(set(seen)) == 5


async def test_editar_movimento_do_tribunal_retorna_403(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    gestor, headers, lawsuit_id = await _setup(client, make_user)
    movement_id = await _seed_tribunal(
        app_session_factory, gestor.tenant_id, lawsuit_id, "Juntada", _BASE_TIME
    )

    put_response = await client.put(
        f"/api/v1/lawsuits/{lawsuit_id}/movements/{movement_id}",
        json={"occurred_at": _BASE_TIME.isoformat(), "title": "Editada", "body": None},
        headers=headers,
    )
    assert put_response.status_code == 403

    delete_response = await client.delete(
        f"/api/v1/lawsuits/{lawsuit_id}/movements/{movement_id}", headers=headers
    )
    assert delete_response.status_code == 403


async def test_editar_movimento_manual_funciona(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor, headers, lawsuit_id = await _setup(client, make_user)
    movement = await _add_manual(client, headers, lawsuit_id, "Nota original", _BASE_TIME)

    update_response = await client.put(
        f"/api/v1/lawsuits/{lawsuit_id}/movements/{movement['id']}",
        json={
            "occurred_at": (_BASE_TIME + timedelta(hours=1)).isoformat(),
            "title": "Nota editada",
            "body": "Detalhe",
        },
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "Nota editada"

    # Regra 4: outro usuário (não autor, não administrador) não edita.
    outro = await make_user(role=UserRole.COLABORADOR, tenant_id=gestor.tenant_id)
    forbidden = await client.put(
        f"/api/v1/lawsuits/{lawsuit_id}/movements/{movement['id']}",
        json={"occurred_at": _BASE_TIME.isoformat(), "title": "Invasão", "body": None},
        headers=_auth_header(outro),
    )
    assert forbidden.status_code == 403

    # Mas um ADMINISTRADOR do mesmo tenant edita.
    admin = await make_user(role=UserRole.ADMINISTRADOR, tenant_id=gestor.tenant_id)
    allowed = await client.put(
        f"/api/v1/lawsuits/{lawsuit_id}/movements/{movement['id']}",
        json={"occurred_at": _BASE_TIME.isoformat(), "title": "Editada pelo admin", "body": None},
        headers=_auth_header(admin),
    )
    assert allowed.status_code == 200


async def test_external_id_duplicado_e_rejeitado(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Regra 5: a UNIQUE (tenant, lawsuit, external_id) é o backstop da dedupe do
    # DataJud — reprocessar o mesmo movimento não duplica. O endpoint HTTP de
    # movimentações é manual (não recebe external_id); o mapeamento para 409 chega
    # com a sync na spec 047. Aqui o teste é no mecanismo: segunda inserção quebra.
    gestor, _headers, lawsuit_id = await _setup(client, make_user)
    await _seed_tribunal(
        app_session_factory,
        gestor.tenant_id,
        lawsuit_id,
        "Juntada original",
        _BASE_TIME,
        external_id="datajud-123",
    )

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, gestor.tenant_id)
        session.add(
            LawsuitMovement(
                tenant_id=gestor.tenant_id,
                lawsuit_id=uuid.UUID(lawsuit_id),
                origin=MovementOrigin.TRIBUNAL,
                occurred_at=_BASE_TIME,
                title="Juntada reprocessada",
                external_id="datajud-123",
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()


async def test_timeline_dentro_do_budget_de_queries(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    gestor, headers, lawsuit_id = await _setup(client, make_user)
    for index in range(10):
        await _add_manual(
            client, headers, lawsuit_id, f"Nota {index}", _BASE_TIME + timedelta(hours=index)
        )
    await _seed_tribunal(app_session_factory, gestor.tenant_id, lawsuit_id, "Juntada", _BASE_TIME)

    statements: list[str] = []
    async with app_session_factory() as session:
        # get_bind() na AsyncSession já devolve o Engine/Connection SYNC subjacente.
        bind = session.get_bind()

        @event.listens_for(bind, "before_cursor_execute", named=True)
        def count_statements(
            conn: object, cursor: object, statement: str, **kwargs: object
        ) -> None:
            # set_config é o contexto de tenant (spec 003), não faz parte do budget —
            # a regra 8 mede a agregação em si: get do processo + página + contagem.
            if not e_plumbing(statement):
                statements.append(statement)

        # Simula exatamente o que o endpoint faz: get do processo + página + count.
        from app.domain.lawsuits.service import LawsuitService

        service = LawsuitService(session=session, tenant_id=gestor.tenant_id)
        async with session.begin():
            await set_tenant_context(session, gestor.tenant_id)
            lawsuit = await service.lawsuits.get_by_id(uuid.UUID(lawsuit_id))
            assert lawsuit is not None
            page = await service.list_timeline(
                lawsuit.id,
                kinds=["movement_auto", "movement_manual"],
                cursor=None,
                limit=20,
            )
            assert page.total == 11

    # Regra 8: nunca N+1 — 11 itens na página e continuam 3 statements
    # (get + count + página), não 1 + 11.
    assert len(statements) <= 3


async def test_timeline_isolada_entre_tenants(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    gestor_a, headers_a, lawsuit_id = await _setup(client, make_user)
    movement = await _add_manual(client, headers_a, lawsuit_id, "Nota de A", _BASE_TIME)

    gestor_b = await make_user(role=UserRole.GESTOR)
    headers_b = _auth_header(gestor_b)

    timeline_response = await client.get(
        f"/api/v1/lawsuits/{lawsuit_id}/timeline", headers=headers_b
    )
    assert timeline_response.status_code == 404

    update_response = await client.put(
        f"/api/v1/lawsuits/{lawsuit_id}/movements/{movement['id']}",
        json={"occurred_at": _BASE_TIME.isoformat(), "title": "Invasão", "body": None},
        headers=headers_b,
    )
    assert update_response.status_code == 404


async def test_preferencias_de_timeline_persistem_por_usuario(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    # Regra 7: a seleção de tipos é preferência do usuário, não do tenant nem do processo.
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)

    put_response = await client.put(
        "/api/v1/users/me/preferences",
        json={"preferences": {"lawsuit_timeline_kinds": ["movement_manual"]}},
        headers=headers,
    )
    assert put_response.status_code == 200

    get_response = await client.get("/api/v1/users/me/preferences", headers=headers)
    assert get_response.json()["preferences"]["lawsuit_timeline_kinds"] == ["movement_manual"]

    # Merge: outra chave não apaga a primeira.
    await client.put(
        "/api/v1/users/me/preferences",
        json={"preferences": {"outra_chave": True}},
        headers=headers,
    )
    merged = (await client.get("/api/v1/users/me/preferences", headers=headers)).json()[
        "preferences"
    ]
    assert merged["lawsuit_timeline_kinds"] == ["movement_manual"]
    assert merged["outra_chave"] is True
