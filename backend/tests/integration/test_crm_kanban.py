"""CRM: board Kanban (spec 051, §8) — as 9 colunas, mover com histórico, RBAC,
paginação por coluna e o orçamento de queries do board."""

import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.lawsuits.board_service import BoardService
from app.domain.lawsuits.listing import LawsuitFilters
from app.domain.lawsuits.models import Lawsuit, LawsuitStageHistory
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import _auth_header, _create_lawsuit, _create_stage
from tests.integration.test_lawsuits_listing import LawsuitFactory
from tests.integration.test_lawsuits_listing import factory as factory  # noqa: F401 (fixture)

_MARKETING_STEP_ID = 1
_NEGOTIATION_STEP_ID = 2

SessionFactory = async_sessionmaker[AsyncSession]


async def _get_lawsuit(factory: LawsuitFactory, lawsuit_id: str) -> Lawsuit:
    async with factory.sessions() as session:
        await set_tenant_context(session, factory.gestor.tenant_id)
        lawsuit = await session.get(Lawsuit, uuid.UUID(lawsuit_id))
        assert lawsuit is not None
        return lawsuit


async def _history_for(factory: LawsuitFactory, lawsuit_id: str) -> list[LawsuitStageHistory]:
    async with factory.sessions() as session:
        await set_tenant_context(session, factory.gestor.tenant_id)
        rows = await session.scalars(
            select(LawsuitStageHistory)
            .where(LawsuitStageHistory.lawsuit_id == uuid.UUID(lawsuit_id))
            .order_by(LawsuitStageHistory.changed_at)
        )
        return list(rows.all())


async def test_board_retorna_9_colunas_inclusive_vazias(factory: LawsuitFactory) -> None:
    response = await factory.client.get("/api/v1/crm/board", headers=factory.headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body["columns"]) == 9
    assert [column["step_id"] for column in body["columns"]] == list(range(1, 10))
    assert all(column["total"] == 0 and column["items"] == [] for column in body["columns"])
    assert body["total"] == 0
    assert body["suggest_refine_filters"] is False


async def test_mover_grava_historico(factory: LawsuitFactory) -> None:
    lawsuit_id = await factory.create("Processo Kanban")
    target_stage = await _create_stage(
        factory.client, factory.headers, step_id=_NEGOTIATION_STEP_ID
    )
    original = await _get_lawsuit(factory, lawsuit_id)

    response = await factory.client.post(
        f"/api/v1/lawsuits/{lawsuit_id}/move-stage",
        json={"stage_id": target_stage},
        headers=factory.headers,
    )
    assert response.status_code == 200
    assert response.json()["stage_id"] == target_stage
    assert response.json()["step_id"] == _NEGOTIATION_STEP_ID

    history = await _history_for(factory, lawsuit_id)
    assert len(history) == 1
    assert history[0].from_stage_id == original.stage_id
    assert str(history[0].to_stage_id) == target_stage
    assert history[0].changed_by == factory.gestor.user_id


async def test_mover_para_primeira_etapa_da_fase(factory: LawsuitFactory) -> None:
    """Regra 3: o front resolve "primeira etapa da fase destino, por position" antes
    de chamar — aqui provamos que as etapas de uma fase saem ordenadas por `position`
    (a primeira criada é a primeira da lista) e que mover para ela funciona ponta a
    ponta."""
    lawsuit_id = await factory.create("Processo Primeira Etapa")
    first_stage = await _create_stage(factory.client, factory.headers, step_id=_NEGOTIATION_STEP_ID)
    await _create_stage(factory.client, factory.headers, step_id=_NEGOTIATION_STEP_ID)

    stages_response = await factory.client.get(
        "/api/v1/stages", params={"step_id": _NEGOTIATION_STEP_ID}, headers=factory.headers
    )
    assert stages_response.status_code == 200
    ordered = stages_response.json()["items"]
    negotiation_ids = [s["id"] for s in ordered if s["step_id"] == _NEGOTIATION_STEP_ID]
    assert negotiation_ids[0] == first_stage  # a criada primeiro tem a menor position

    move = await factory.client.post(
        f"/api/v1/lawsuits/{lawsuit_id}/move-stage",
        json={"stage_id": first_stage},
        headers=factory.headers,
    )
    assert move.status_code == 200
    assert move.json()["stage_id"] == first_stage


async def test_trigger_atualiza_stage_entered_at(factory: LawsuitFactory) -> None:
    lawsuit_id = await factory.create("Processo Trigger")
    before = await _get_lawsuit(factory, lawsuit_id)
    target_stage = await _create_stage(
        factory.client, factory.headers, step_id=_NEGOTIATION_STEP_ID
    )

    response = await factory.client.post(
        f"/api/v1/lawsuits/{lawsuit_id}/move-stage",
        json={"stage_id": target_stage},
        headers=factory.headers,
    )
    assert response.status_code == 200

    after = await _get_lawsuit(factory, lawsuit_id)
    assert after.stage_entered_at > before.stage_entered_at

    # Mover pra MESMA etapa não deveria reagendar o relógio (regra 6: só quando o
    # stage_id de fato muda).
    same_stage_response = await factory.client.post(
        f"/api/v1/lawsuits/{lawsuit_id}/move-stage",
        json={"stage_id": target_stage},
        headers=factory.headers,
    )
    assert same_stage_response.status_code == 200
    unchanged = await _get_lawsuit(factory, lawsuit_id)
    assert unchanged.stage_entered_at == after.stage_entered_at


async def test_mudanca_fora_do_kanban_tambem_grava_historico(factory: LawsuitFactory) -> None:
    lawsuit_id = await factory.create("Processo PUT")
    target_stage = await _create_stage(
        factory.client, factory.headers, step_id=_NEGOTIATION_STEP_ID
    )

    response = await factory.client.put(
        f"/api/v1/lawsuits/{lawsuit_id}",
        json={
            "user_id": str(factory.gestor.user_id),
            "lawsuit_type_id": factory.type_id,
            "stage_id": target_stage,
        },
        headers=factory.headers,
    )
    assert response.status_code == 200

    history = await _history_for(factory, lawsuit_id)
    assert len(history) == 1
    assert str(history[0].to_stage_id) == target_stage
    assert history[0].changed_by == factory.gestor.user_id


async def test_colaborador_move_so_processo_alheio_da_403(
    factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor_lawsuit_id = await factory.create("Processo do Gestor")
    colaborador = await make_user(role=UserRole.COLABORADOR, tenant_id=factory.gestor.tenant_id)
    colaborador_headers = _auth_header(colaborador)
    # Criado pelo GESTOR (Colaborador não tem permissão pra criar contato/origem), com
    # o Colaborador como RESPONSÁVEL — é isso que a regra 10 olha, não quem criou.
    own_lawsuit = await _create_lawsuit(
        factory.client,
        factory.headers,
        user_id=str(colaborador.user_id),
        lawsuit_type_id=factory.type_id,
        stage_id=factory.stage_id,
    )
    target_stage = await _create_stage(
        factory.client, factory.headers, step_id=_NEGOTIATION_STEP_ID
    )

    forbidden = await factory.client.post(
        f"/api/v1/lawsuits/{gestor_lawsuit_id}/move-stage",
        json={"stage_id": target_stage},
        headers=colaborador_headers,
    )
    assert forbidden.status_code == 403

    allowed = await factory.client.post(
        f"/api/v1/lawsuits/{own_lawsuit['id']}/move-stage",
        json={"stage_id": target_stage},
        headers=colaborador_headers,
    )
    assert allowed.status_code == 200


async def test_acao_em_massa_e_transacional(factory: LawsuitFactory) -> None:
    lawsuit_a = await factory.create("Lote A")
    lawsuit_b = await factory.create("Lote B")
    target_stage = await _create_stage(
        factory.client, factory.headers, step_id=_NEGOTIATION_STEP_ID
    )
    bogus_id = str(uuid.uuid4())

    response = await factory.client.post(
        "/api/v1/lawsuits/bulk/move-stage",
        json={"lawsuit_ids": [lawsuit_a, lawsuit_b, bogus_id], "stage_id": target_stage},
        headers=factory.headers,
    )
    assert response.status_code == 404

    # Nenhum dos dois válidos mudou — tudo ou nada.
    for lawsuit_id in (lawsuit_a, lawsuit_b):
        lawsuit = await _get_lawsuit(factory, lawsuit_id)
        assert str(lawsuit.stage_id) == factory.stage_id

    ok_response = await factory.client.post(
        "/api/v1/lawsuits/bulk/move-stage",
        json={"lawsuit_ids": [lawsuit_a, lawsuit_b], "stage_id": target_stage},
        headers=factory.headers,
    )
    assert ok_response.status_code == 200
    assert ok_response.json()["moved"] == 2
    for lawsuit_id in (lawsuit_a, lawsuit_b):
        lawsuit = await _get_lawsuit(factory, lawsuit_id)
        assert str(lawsuit.stage_id) == target_stage


async def test_paginacao_por_coluna(factory: LawsuitFactory) -> None:
    ids = [await factory.create(f"Coluna {index}") for index in range(3)]
    _ = ids

    first_page = await factory.client.get(
        f"/api/v1/crm/board/column/{_MARKETING_STEP_ID}",
        params={"limit": 2},
        headers=factory.headers,
    )
    assert first_page.status_code == 200
    body = first_page.json()
    assert len(body["items"]) == 2
    assert body["total"] == 3
    assert body["next_cursor"] is not None

    second_page = await factory.client.get(
        f"/api/v1/crm/board/column/{_MARKETING_STEP_ID}",
        params={"limit": 2, "cursor": body["next_cursor"]},
        headers=factory.headers,
    )
    assert second_page.status_code == 200
    second_body = second_page.json()
    assert len(second_body["items"]) == 1
    assert second_body["next_cursor"] is None

    seen_ids = {item["id"] for item in body["items"]} | {
        item["id"] for item in second_body["items"]
    }
    assert seen_ids == set(ids)


async def test_board_fica_dentro_do_orcamento_de_queries(factory: LawsuitFactory) -> None:
    await factory.create("Budget Kanban 1")
    await factory.create("Budget Kanban 2")

    statements: list[str] = []
    async with factory.sessions() as session:
        bind = session.get_bind()

        @event.listens_for(bind, "before_cursor_execute", named=True)
        def count_statements(conn: object, cursor: object, statement: str, **kw: object) -> None:
            if "set_config" not in statement:
                statements.append(statement)

        service = BoardService(session=session, tenant_id=factory.gestor.tenant_id)
        async with session.begin():
            await set_tenant_context(session, factory.gestor.tenant_id)
            board = await service.get_board(filters=LawsuitFilters())
            assert board.total == 2

    # Regra do §8: 2 statements de dados (contagens + cards) — StepRepository.list_all
    # (router, não o service) soma 1 quando exposto por HTTP; aqui é só o service.
    assert len(statements) <= 3
