"""Módulo Intimações — listagem, filtros, leitura e vínculo manual (spec 048, §8)."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.publications.models import Publication, PublicationRecipient
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import (
    _auth_header,
    _create_lawsuit,
    _create_lawsuit_type,
    _create_stage,
)

SessionFactory = async_sessionmaker[AsyncSession]
TODAY = date.today


@dataclass
class PubSetup:
    client: AsyncClient
    sessions: SessionFactory
    gestor: SeededUser
    headers: dict[str, str]


@pytest.fixture
async def setup(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: SessionFactory,
) -> PubSetup:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    return PubSetup(client, app_session_factory, gestor, headers)


async def make_publication(
    factory: SessionFactory,
    tenant_id: uuid.UUID,
    *,
    availability_date: date | None = None,
    court_code: str = "TJSP",
    process_number: str | None = None,
    routed_to: uuid.UUID | None = None,
    lawsuit_id: uuid.UUID | None = None,
    is_active: bool = True,
    cancellation_reason: str | None = None,
    parties: list[str] | None = None,
) -> uuid.UUID:
    async with factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        publication = Publication(
            tenant_id=tenant_id,
            external_id=abs(hash(uuid.uuid4())) % 1_000_000,
            hash=f"listing-test-{uuid.uuid4().hex}",
            availability_date=availability_date or TODAY(),
            court_code=court_code,
            body="Texto da publicação de teste.",
            process_number=process_number,
            routed_to=routed_to,
            lawsuit_id=lawsuit_id,
            is_active=is_active,
            cancellation_reason=cancellation_reason,
            raw_payload={},
        )
        session.add(publication)
        await session.flush()
        for name in parties or []:
            session.add(
                PublicationRecipient(
                    tenant_id=tenant_id, publication_id=publication.id, name=name, pole="A"
                )
            )
        await session.flush()
        return publication.id


async def test_filtro_por_intervalo(setup: PubSetup) -> None:
    today = TODAY()
    await make_publication(setup.sessions, setup.gestor.tenant_id, availability_date=today)
    await make_publication(
        setup.sessions, setup.gestor.tenant_id, availability_date=today - timedelta(days=2)
    )
    await make_publication(
        setup.sessions, setup.gestor.tenant_id, availability_date=today - timedelta(days=5)
    )
    await make_publication(
        setup.sessions, setup.gestor.tenant_id, availability_date=today - timedelta(days=10)
    )

    only_today = await setup.client.get(
        "/api/v1/publications", params={"interval": "today"}, headers=setup.headers
    )
    assert only_today.status_code == 200
    assert only_today.json()["total"] == 1

    last_3d = await setup.client.get(
        "/api/v1/publications", params={"interval": "3d"}, headers=setup.headers
    )
    assert last_3d.json()["total"] == 2

    last_7d = await setup.client.get(
        "/api/v1/publications", params={"interval": "7d"}, headers=setup.headers
    )
    assert last_7d.json()["total"] == 3

    custom = await setup.client.get(
        "/api/v1/publications",
        params={
            "interval": "custom",
            "date_from": (today - timedelta(days=10)).isoformat(),
            "date_to": (today - timedelta(days=10)).isoformat(),
        },
        headers=setup.headers,
    )
    assert custom.json()["total"] == 1


async def test_filtro_linked_false(setup: PubSetup) -> None:
    type_id, _group_id = await _create_lawsuit_type(setup.client, setup.headers)
    stage_id = await _create_stage(setup.client, setup.headers)
    lawsuit = await _create_lawsuit(
        setup.client,
        setup.headers,
        user_id=str(setup.gestor.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
    )
    linked_id = await make_publication(
        setup.sessions, setup.gestor.tenant_id, lawsuit_id=uuid.UUID(str(lawsuit["id"]))
    )
    unlinked_id = await make_publication(setup.sessions, setup.gestor.tenant_id)

    response = await setup.client.get(
        "/api/v1/publications", params={"linked": "false"}, headers=setup.headers
    )
    ids = {item["id"] for item in response.json()["items"]}
    assert unlinked_id in {uuid.UUID(i) for i in ids}
    assert linked_id not in {uuid.UUID(i) for i in ids}


async def test_filtro_por_tribunal_e_responsavel(
    setup: PubSetup, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    outro = await make_user(tenant_id=setup.gestor.tenant_id, role=UserRole.COLABORADOR)
    tjsp_id = await make_publication(setup.sessions, setup.gestor.tenant_id, court_code="TJSP")
    await make_publication(setup.sessions, setup.gestor.tenant_id, court_code="TJRJ")
    routed_id = await make_publication(
        setup.sessions, setup.gestor.tenant_id, routed_to=outro.user_id
    )

    by_court = await setup.client.get(
        "/api/v1/publications", params={"court_code": "TJSP"}, headers=setup.headers
    )
    court_ids = {item["id"] for item in by_court.json()["items"]}
    assert str(tjsp_id) in court_ids

    by_user = await setup.client.get(
        "/api/v1/publications", params={"user_id": str(outro.user_id)}, headers=setup.headers
    )
    user_ids = {item["id"] for item in by_user.json()["items"]}
    assert user_ids == {str(routed_id)}


async def test_busca_por_numero_com_e_sem_mascara(setup: PubSetup) -> None:
    digits = "12345678920268260100"
    await make_publication(setup.sessions, setup.gestor.tenant_id, process_number=digits)

    masked = await setup.client.get(
        "/api/v1/publications",
        params={"process_number": "1234567-89.2026.8.26.0100"},
        headers=setup.headers,
    )
    assert masked.json()["total"] == 1

    unmasked = await setup.client.get(
        "/api/v1/publications", params={"process_number": digits}, headers=setup.headers
    )
    assert unmasked.json()["total"] == 1


async def test_leitura_e_por_usuario(
    setup: PubSetup, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    outro = await make_user(tenant_id=setup.gestor.tenant_id, role=UserRole.COLABORADOR)
    outro_headers = _auth_header(outro)
    publication_id = await make_publication(setup.sessions, setup.gestor.tenant_id)

    read_response = await setup.client.post(
        f"/api/v1/publications/{publication_id}/read", headers=setup.headers
    )
    assert read_response.status_code == 200
    assert read_response.json()["is_read"] is True

    as_gestor = await setup.client.get(
        "/api/v1/publications", params={"read": "true"}, headers=setup.headers
    )
    assert {item["id"] for item in as_gestor.json()["items"]} == {str(publication_id)}

    as_outro = await setup.client.get(
        "/api/v1/publications", params={"read": "true"}, headers=outro_headers
    )
    assert as_outro.json()["total"] == 0

    detail_as_outro = await setup.client.get(
        f"/api/v1/publications/{publication_id}", headers=outro_headers
    )
    assert detail_as_outro.json()["is_read"] is False


async def test_vinculo_manual_cria_a_tarefa(setup: PubSetup) -> None:
    response = await setup.client.post(
        "/api/v1/task-types",
        json={"name": "Intimações Judiciais", "reward": 5},
        headers=setup.headers,
    )
    assert response.status_code == 201
    type_id, _group_id = await _create_lawsuit_type(setup.client, setup.headers)
    stage_id = await _create_stage(setup.client, setup.headers)
    lawsuit = await _create_lawsuit(
        setup.client,
        setup.headers,
        user_id=str(setup.gestor.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
    )
    publication_id = await make_publication(setup.sessions, setup.gestor.tenant_id)

    link_response = await setup.client.post(
        f"/api/v1/publications/{publication_id}/link",
        json={"lawsuit_id": lawsuit["id"]},
        headers=setup.headers,
    )
    assert link_response.status_code == 200, link_response.text
    assert link_response.json()["post_id"] is not None


async def test_cancelada_continua_listada_com_motivo(setup: PubSetup) -> None:
    cancelled_id = await make_publication(
        setup.sessions,
        setup.gestor.tenant_id,
        is_active=False,
        cancellation_reason="Publicação anulada a pedido da parte",
    )
    active_id = await make_publication(setup.sessions, setup.gestor.tenant_id)

    default_view = await setup.client.get("/api/v1/publications", headers=setup.headers)
    ids = {item["id"]: item for item in default_view.json()["items"]}
    assert str(cancelled_id) in ids  # regra 3: nunca some da lista
    assert ids[str(cancelled_id)]["cancellation_reason"] == "Publicação anulada a pedido da parte"

    only_cancelled = await setup.client.get(
        "/api/v1/publications", params={"cancelled": "true"}, headers=setup.headers
    )
    assert {item["id"] for item in only_cancelled.json()["items"]} == {str(cancelled_id)}

    only_active = await setup.client.get(
        "/api/v1/publications", params={"cancelled": "false"}, headers=setup.headers
    )
    assert str(active_id) in {item["id"] for item in only_active.json()["items"]}
    assert str(cancelled_id) not in {item["id"] for item in only_active.json()["items"]}


async def test_contadores_em_query_unica(setup: PubSetup) -> None:
    type_id, _group_id = await _create_lawsuit_type(setup.client, setup.headers)
    stage_id = await _create_stage(setup.client, setup.headers)
    lawsuit = await _create_lawsuit(
        setup.client,
        setup.headers,
        user_id=str(setup.gestor.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
    )
    await make_publication(setup.sessions, setup.gestor.tenant_id)  # não vinculada
    await make_publication(setup.sessions, setup.gestor.tenant_id)  # não vinculada
    await make_publication(
        setup.sessions, setup.gestor.tenant_id, lawsuit_id=uuid.UUID(str(lawsuit["id"]))
    )
    cancelled_id = await make_publication(
        setup.sessions, setup.gestor.tenant_id, is_active=False, cancellation_reason="Anulada"
    )
    read_id = await make_publication(setup.sessions, setup.gestor.tenant_id)
    await setup.client.post(f"/api/v1/publications/{read_id}/read", headers=setup.headers)

    response = await setup.client.get("/api/v1/publications/counts", headers=setup.headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert body["unlinked"] == 4  # as 2 não vinculadas + a cancelada + a lida
    assert body["cancelled"] == 1
    assert body["unread"] == 4
    assert cancelled_id is not None


async def test_keyset_estavel(setup: PubSetup) -> None:
    today = TODAY()
    created_ids = []
    for offset in range(5):
        created_ids.append(
            await make_publication(
                setup.sessions,
                setup.gestor.tenant_id,
                availability_date=today - timedelta(days=offset),
            )
        )

    seen: list[str] = []
    cursor = None
    for _ in range(10):
        params: dict[str, str] = {"limit": "2", "interval": "custom", "date_from": "2020-01-01"}
        if cursor:
            params["cursor"] = cursor
        response = await setup.client.get(
            "/api/v1/publications", params=params, headers=setup.headers
        )
        body = response.json()
        seen += [item["id"] for item in body["items"]]
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert len(seen) == len(set(seen)) == 5
    assert set(seen) == {str(pub_id) for pub_id in created_ids}
