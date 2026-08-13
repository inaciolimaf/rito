"""Intimação → tarefa (spec 045, §8): as 3 estratégias de casamento e as 4 rotas
de roteamento são a espinha dorsal desta spec — nenhuma fica sem teste.

Casamento/roteamento roda direto no service (como o worker chamaria); os
endpoints de vínculo manual e reprocessamento passam pelo `client` HTTP para
exercitar o contrato real (§6).
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.lawsuits.cnj import compute_check_digit
from app.domain.posts.models import Post, PostUser
from app.domain.publications.models import Publication, PublicationLawyer
from app.domain.publications.routing import PublicationRoutingService
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser
from tests.integration.test_account import _valid_payload as _account_payload
from tests.integration.test_lawsuits import (
    _auth_header,
    _create_lawsuit,
    _create_lawsuit_type,
    _create_stage,
)

SessionFactory = async_sessionmaker[AsyncSession]

_TASK_TYPE_NAME = "Intimações Judiciais"


def _cnj(seq: int) -> str:
    """Número CNJ válido e determinístico (dígito verificador real — spec 025) para
    não colidir com a validação de `LawsuitService.create` nos testes de roteamento."""
    sequential, year, segment, court, origin = f"{seq:07d}", "2026", "8", "26", "0100"
    digits18 = sequential + year + segment + court + origin
    return sequential + compute_check_digit(digits18) + year + segment + court + origin


def _masked(digits: str) -> str:
    return (
        f"{digits[0:7]}-{digits[7:9]}.{digits[9:13]}."
        f"{digits[13:14]}.{digits[14:16]}.{digits[16:20]}"
    )


@dataclass
class RoutingSetup:
    client: AsyncClient
    sessions: SessionFactory
    gestor: SeededUser
    headers: dict[str, str]
    type_id: str
    group_id: str
    stage_id: str

    async def create_lawsuit(
        self, *, user_id: uuid.UUID, process_number: str | None = None
    ) -> uuid.UUID:
        lawsuit = await _create_lawsuit(
            self.client,
            self.headers,
            user_id=str(user_id),
            lawsuit_type_id=self.type_id,
            stage_id=self.stage_id,
            process_number=process_number,
        )
        return uuid.UUID(str(lawsuit["id"]))

    async def archive(self, lawsuit_id: uuid.UUID) -> None:
        async with self.sessions() as session, session.begin():
            await set_tenant_context(session, self.gestor.tenant_id)
            await session.execute(
                text("UPDATE lawsuits SET is_archived = true WHERE id = CAST(:id AS uuid)"),
                {"id": str(lawsuit_id)},
            )

    async def set_group_responsible(self, user_id: uuid.UUID) -> None:
        response = await self.client.put(
            f"/api/v1/action-groups/{self.group_id}",
            json={"name": f"Grupo {self.group_id}", "publications_user_id": str(user_id)},
            headers=self.headers,
        )
        assert response.status_code == 200, response.text

    async def set_account_default(self, user_id: uuid.UUID) -> None:
        # A conta (spec 011) precisa existir antes de configurar a rota 3 — o
        # onboarding real cria a conta bem antes de ligar o monitoramento de intimações.
        account = await self.client.put(
            "/api/v1/account", json=_account_payload(), headers=self.headers
        )
        assert account.status_code == 200, account.text
        response = await self.client.put(
            "/api/v1/account/publications-settings",
            json={"default_publications_user_id": str(user_id)},
            headers=self.headers,
        )
        assert response.status_code == 200, response.text

    async def create_term(self, *, oab_number: str, oab_state: str, user_id: uuid.UUID) -> None:
        response = await self.client.post(
            "/api/v1/monitored-terms",
            json={
                "kind": "OAB",
                "value": oab_number,
                "oab_state": oab_state,
                "user_id": str(user_id),
            },
            headers=self.headers,
        )
        assert response.status_code == 201, response.text


@pytest.fixture
async def setup(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: SessionFactory,
) -> RoutingSetup:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    type_id, group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    response = await client.post(
        "/api/v1/task-types", json={"name": _TASK_TYPE_NAME, "reward": 5}, headers=headers
    )
    assert response.status_code == 201, response.text
    return RoutingSetup(client, app_session_factory, gestor, headers, type_id, group_id, stage_id)


async def make_publication(
    factory: SessionFactory,
    tenant_id: uuid.UUID,
    *,
    process_number: str | None = None,
    link: str | None = None,
    lawyers: list[tuple[str, str]] | None = None,
) -> uuid.UUID:
    async with factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        publication = Publication(
            tenant_id=tenant_id,
            external_id=abs(hash(uuid.uuid4())) % 1_000_000,
            hash=f"routing-test-{uuid.uuid4().hex}",
            availability_date=date(2026, 8, 1),
            court_code="TJSP",
            body="Texto da publicação de teste.",
            process_number=process_number,
            link=link,
            raw_payload={},
        )
        session.add(publication)
        await session.flush()
        for index, (oab_number, oab_state) in enumerate(lawyers or []):
            session.add(
                PublicationLawyer(
                    tenant_id=tenant_id,
                    publication_id=publication.id,
                    external_lawyer_id=1_000 + index,
                    name=f"Advogado {index}",
                    oab_number=oab_number,
                    oab_state=oab_state,
                )
            )
        await session.flush()
        return publication.id


async def route(
    factory: SessionFactory, tenant_id: uuid.UUID, publication_id: uuid.UUID
) -> Publication:
    async with factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        publication = await session.get(Publication, publication_id)
        assert publication is not None
        service = PublicationRoutingService(session, tenant_id)
        return await service.route(publication)


async def fetch_publication(
    factory: SessionFactory, tenant_id: uuid.UUID, publication_id: uuid.UUID
) -> Publication:
    async with factory() as session:
        await set_tenant_context(session, tenant_id)
        publication = await session.get(Publication, publication_id)
        assert publication is not None
        _ = (
            publication.lawsuit_id,
            publication.matched_by,
            publication.routed_to,
            publication.routed_by,
            publication.post_id,
            publication.processed_at,
        )
        return publication


async def fetch_post(factory: SessionFactory, tenant_id: uuid.UUID, post_id: uuid.UUID) -> Post:
    async with factory() as session:
        await set_tenant_context(session, tenant_id)
        post = await session.get(Post, post_id)
        assert post is not None
        _ = (post.scheduled_date, post.deadline_date, post.comments, post.is_urgent)
        return post


async def count_posts(factory: SessionFactory, tenant_id: uuid.UUID) -> int:
    async with factory() as session:
        await set_tenant_context(session, tenant_id)
        rows = await session.scalars(select(Post))
        return len(rows.all())


async def assignee_ids(
    factory: SessionFactory, tenant_id: uuid.UUID, post_id: uuid.UUID
) -> set[uuid.UUID]:
    async with factory() as session:
        await set_tenant_context(session, tenant_id)
        rows = await session.scalars(select(PostUser.user_id).where(PostUser.post_id == post_id))
        return set(rows.all())


async def test_casa_por_numero_de_processo(setup: RoutingSetup) -> None:
    number = _cnj(1)
    lawsuit_id = await setup.create_lawsuit(user_id=setup.gestor.user_id, process_number=number)
    publication_id = await make_publication(
        setup.sessions, setup.gestor.tenant_id, process_number=number
    )

    routed = await route(setup.sessions, setup.gestor.tenant_id, publication_id)

    assert routed.matched_by == "process_number"
    assert routed.lawsuit_id == lawsuit_id


async def test_casa_por_advogado_quando_numero_nao_bate(
    setup: RoutingSetup, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    segundo = await make_user(tenant_id=setup.gestor.tenant_id, role=UserRole.COLABORADOR)
    await setup.create_term(oab_number="222222", oab_state="SP", user_id=segundo.user_id)
    lawsuit_id = await setup.create_lawsuit(user_id=segundo.user_id, process_number=None)
    publication_id = await make_publication(
        setup.sessions,
        setup.gestor.tenant_id,
        process_number="99999999999999999999",  # não bate com nenhum processo
        lawyers=[("222222", "SP")],
    )

    routed = await route(setup.sessions, setup.gestor.tenant_id, publication_id)

    assert routed.matched_by == "lawyer_id"
    assert routed.lawsuit_id == lawsuit_id


async def test_sem_casamento_fica_nao_vinculada_sem_tarefa(setup: RoutingSetup) -> None:
    publication_id = await make_publication(setup.sessions, setup.gestor.tenant_id)

    routed = await route(setup.sessions, setup.gestor.tenant_id, publication_id)

    assert routed.lawsuit_id is None
    assert routed.post_id is None
    assert routed.processed_at is not None


async def test_numero_ambiguo_fica_nao_vinculada_com_motivo(setup: RoutingSetup) -> None:
    number = _cnj(4)
    await setup.create_lawsuit(user_id=setup.gestor.user_id, process_number=number)
    await setup.create_lawsuit(user_id=setup.gestor.user_id, process_number=number)
    publication_id = await make_publication(
        setup.sessions, setup.gestor.tenant_id, process_number=number
    )

    routed = await route(setup.sessions, setup.gestor.tenant_id, publication_id)

    assert routed.lawsuit_id is None
    assert routed.matched_by == "ambiguous"
    assert routed.post_id is None


async def test_rota_1_responsavel_do_grupo_de_acao(
    setup: RoutingSetup, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    responsavel = await make_user(tenant_id=setup.gestor.tenant_id, role=UserRole.COLABORADOR)
    await setup.set_group_responsible(responsavel.user_id)
    number = _cnj(5)
    await setup.create_lawsuit(user_id=setup.gestor.user_id, process_number=number)
    publication_id = await make_publication(
        setup.sessions, setup.gestor.tenant_id, process_number=number
    )

    routed = await route(setup.sessions, setup.gestor.tenant_id, publication_id)

    assert routed.routed_by == "action_group"
    assert routed.routed_to == responsavel.user_id
    assert routed.post_id is not None
    assert await assignee_ids(setup.sessions, setup.gestor.tenant_id, routed.post_id) == {
        responsavel.user_id
    }


async def test_rota_2_responsavel_do_termo(
    setup: RoutingSetup, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    responsavel = await make_user(tenant_id=setup.gestor.tenant_id, role=UserRole.COLABORADOR)
    await setup.create_term(oab_number="333333", oab_state="RJ", user_id=responsavel.user_id)
    number = _cnj(6)
    await setup.create_lawsuit(user_id=setup.gestor.user_id, process_number=number)
    publication_id = await make_publication(
        setup.sessions,
        setup.gestor.tenant_id,
        process_number=number,
        lawyers=[("333333", "RJ")],
    )

    routed = await route(setup.sessions, setup.gestor.tenant_id, publication_id)

    assert routed.routed_by == "term_user"
    assert routed.routed_to == responsavel.user_id


async def test_rota_3_responsavel_geral_da_conta(
    setup: RoutingSetup, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    responsavel = await make_user(tenant_id=setup.gestor.tenant_id, role=UserRole.COLABORADOR)
    await setup.set_account_default(responsavel.user_id)
    number = _cnj(7)
    await setup.create_lawsuit(user_id=setup.gestor.user_id, process_number=number)
    publication_id = await make_publication(
        setup.sessions, setup.gestor.tenant_id, process_number=number
    )

    routed = await route(setup.sessions, setup.gestor.tenant_id, publication_id)

    assert routed.routed_by == "general"
    assert routed.routed_to == responsavel.user_id


async def test_rota_4_fallback_para_gestor(setup: RoutingSetup) -> None:
    number = _cnj(8)
    await setup.create_lawsuit(user_id=setup.gestor.user_id, process_number=number)
    publication_id = await make_publication(
        setup.sessions, setup.gestor.tenant_id, process_number=number
    )

    routed = await route(setup.sessions, setup.gestor.tenant_id, publication_id)

    assert routed.routed_by == "gestor_fallback"
    assert routed.routed_to == setup.gestor.user_id


async def test_reprocessar_nao_duplica_tarefa(setup: RoutingSetup) -> None:
    number = _cnj(9)
    await setup.create_lawsuit(user_id=setup.gestor.user_id, process_number=number)
    publication_id = await make_publication(
        setup.sessions, setup.gestor.tenant_id, process_number=number
    )

    first = await setup.client.post(
        f"/api/v1/publications/{publication_id}/reprocess", headers=setup.headers
    )
    assert first.status_code == 200
    post_id = first.json()["post_id"]
    assert post_id is not None

    second = await setup.client.post(
        f"/api/v1/publications/{publication_id}/reprocess", headers=setup.headers
    )
    assert second.status_code == 200
    assert second.json()["post_id"] == post_id
    assert await count_posts(setup.sessions, setup.gestor.tenant_id) == 1


async def test_vinculo_manual_cria_a_tarefa(setup: RoutingSetup) -> None:
    lawsuit_id = await setup.create_lawsuit(user_id=setup.gestor.user_id)
    publication_id = await make_publication(setup.sessions, setup.gestor.tenant_id)

    response = await setup.client.post(
        f"/api/v1/publications/{publication_id}/link",
        json={"lawsuit_id": str(lawsuit_id)},
        headers=setup.headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["matched_by"] == "manual"
    assert body["lawsuit_id"] == str(lawsuit_id)
    assert body["post_id"] is not None


async def test_scheduled_date_igual_availability_date(setup: RoutingSetup) -> None:
    number = _cnj(11)
    await setup.create_lawsuit(user_id=setup.gestor.user_id, process_number=number)
    publication_id = await make_publication(
        setup.sessions, setup.gestor.tenant_id, process_number=number
    )

    routed = await route(setup.sessions, setup.gestor.tenant_id, publication_id)
    assert routed.post_id is not None
    post = await fetch_post(setup.sessions, setup.gestor.tenant_id, routed.post_id)

    assert post.scheduled_date == routed.availability_date


async def test_deadline_date_fica_vazio(setup: RoutingSetup) -> None:
    number = _cnj(12)
    await setup.create_lawsuit(user_id=setup.gestor.user_id, process_number=number)
    publication_id = await make_publication(
        setup.sessions, setup.gestor.tenant_id, process_number=number
    )

    routed = await route(setup.sessions, setup.gestor.tenant_id, publication_id)
    assert routed.post_id is not None
    post = await fetch_post(setup.sessions, setup.gestor.tenant_id, routed.post_id)

    assert post.deadline_date is None


async def test_cancelamento_comenta_e_marca_urgente(setup: RoutingSetup) -> None:
    number = _cnj(13)
    await setup.create_lawsuit(user_id=setup.gestor.user_id, process_number=number)
    publication_id = await make_publication(
        setup.sessions, setup.gestor.tenant_id, process_number=number
    )
    routed = await route(setup.sessions, setup.gestor.tenant_id, publication_id)
    assert routed.post_id is not None

    async with setup.sessions() as session, session.begin():
        await set_tenant_context(session, setup.gestor.tenant_id)
        publication = await session.get(Publication, publication_id)
        assert publication is not None
        publication.is_active = False
        publication.cancellation_reason = "Publicação anulada a pedido da parte"
        publication.cancelled_at = datetime.now(UTC).date()
        service = PublicationRoutingService(session, setup.gestor.tenant_id)
        await service.handle_cancellation(publication)

    post = await fetch_post(setup.sessions, setup.gestor.tenant_id, routed.post_id)
    assert post.is_urgent is True
    assert post.comments is not None and "anulada" in post.comments.lower()


async def test_casamento_ignora_mascara(setup: RoutingSetup) -> None:
    number = _cnj(14)
    lawsuit_id = await setup.create_lawsuit(user_id=setup.gestor.user_id, process_number=number)
    # Regra 9: a publicação chega com máscara (edge case) — o casamento compara só dígitos.
    publication_id = await make_publication(
        setup.sessions, setup.gestor.tenant_id, process_number=_masked(number)
    )

    routed = await route(setup.sessions, setup.gestor.tenant_id, publication_id)

    assert routed.matched_by == "process_number"
    assert routed.lawsuit_id == lawsuit_id


async def test_processo_arquivado_ainda_casa(setup: RoutingSetup) -> None:
    number = _cnj(15)
    lawsuit_id = await setup.create_lawsuit(user_id=setup.gestor.user_id, process_number=number)
    await setup.archive(lawsuit_id)
    publication_id = await make_publication(
        setup.sessions, setup.gestor.tenant_id, process_number=number
    )

    routed = await route(setup.sessions, setup.gestor.tenant_id, publication_id)

    assert routed.matched_by == "process_number"
    assert routed.lawsuit_id == lawsuit_id


async def test_roteamento_dispara_intimacao_quando_configurado(setup: RoutingSetup) -> None:
    rule_response = await setup.client.put(
        "/api/v1/notification-rules/INTIMACAO",
        json={"responsible_user_id": str(setup.gestor.user_id), "channels": []},
        headers=setup.headers,
    )
    assert rule_response.status_code == 200, rule_response.text

    number = _cnj(16)
    await setup.create_lawsuit(user_id=setup.gestor.user_id, process_number=number)
    publication_id = await make_publication(
        setup.sessions, setup.gestor.tenant_id, process_number=number
    )

    routed = await route(setup.sessions, setup.gestor.tenant_id, publication_id)
    assert routed.post_id is not None

    notifications = await setup.client.get("/api/v1/notifications", headers=setup.headers)
    assert notifications.status_code == 200
    kinds = {item["kind"] for item in notifications.json()["items"]}
    assert "INTIMACAO" in kinds
