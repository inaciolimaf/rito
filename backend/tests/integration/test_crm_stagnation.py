"""CRM: estagnação e métricas (spec 052, §8) — cálculo por etapa, reset ao mover,
arquivado nunca estagna, job diário, troca de `stagnant_days`, filtro, stats e o
limite de 1x/hora do recálculo manual."""

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.lawsuits.stagnation_service import StagnationService
from app.domain.stages.repository import StageRepository
from tests.integration.test_crm_kanban import _get_lawsuit
from tests.integration.test_lawsuits import _create_stage
from tests.integration.test_lawsuits_listing import LawsuitFactory
from tests.integration.test_lawsuits_listing import factory as factory  # noqa: F401 (fixture)

SessionFactory = async_sessionmaker[AsyncSession]

_STAGNANT_DAYS = 5


async def _create_stagnant_stage(
    factory: LawsuitFactory, *, stagnant_days: int = _STAGNANT_DAYS
) -> str:
    suffix = uuid.uuid4().hex[:8]
    response = await factory.client.post(
        "/api/v1/stages",
        json={
            "name": f"Estagnação {suffix}",
            "step_id": 1,
            "enable_stagnant_days": True,
            "stagnant_days": stagnant_days,
        },
        headers=factory.headers,
    )
    assert response.status_code == 201, response.text
    result: str = response.json()["id"]
    return result


async def _backdate_stage_entered_at(
    factory: LawsuitFactory, lawsuit_id: str, days_ago: int
) -> None:
    async with factory.sessions() as session, session.begin():
        await set_tenant_context(session, factory.gestor.tenant_id)
        await session.execute(
            text(
                "UPDATE lawsuits SET stage_entered_at = now() - make_interval(days => :days) "
                "WHERE id = CAST(:id AS uuid)"
            ),
            {"days": days_ago, "id": lawsuit_id},
        )


async def _archive(factory: LawsuitFactory, lawsuit_id: str) -> None:
    async with factory.sessions() as session, session.begin():
        await set_tenant_context(session, factory.gestor.tenant_id)
        await session.execute(
            text("UPDATE lawsuits SET is_archived = true WHERE id = CAST(:id AS uuid)"),
            {"id": lawsuit_id},
        )


async def _recalculate_manually(factory: LawsuitFactory) -> dict[str, object]:
    response = await factory.client.post(
        "/api/v1/crm/recalculate-stagnation", headers=factory.headers
    )
    assert response.status_code == 200, response.text
    result: dict[str, object] = response.json()
    return result


async def test_marca_estagnado_ao_passar_do_limite(factory: LawsuitFactory) -> None:
    stage = await _create_stagnant_stage(factory)
    lawsuit_id = await factory.create("Processo Estagnado", stage_id=stage)
    await _backdate_stage_entered_at(factory, lawsuit_id, _STAGNANT_DAYS + 2)

    await _recalculate_manually(factory)

    lawsuit = await _get_lawsuit(factory, lawsuit_id)
    assert lawsuit.is_stagnant is True
    assert lawsuit.stagnant_since is not None


async def test_etapa_sem_configuracao_nunca_marca(factory: LawsuitFactory) -> None:
    lawsuit_id = await factory.create("Processo Sem Regra")
    await _backdate_stage_entered_at(factory, lawsuit_id, 365)

    await _recalculate_manually(factory)

    lawsuit = await _get_lawsuit(factory, lawsuit_id)
    assert lawsuit.is_stagnant is False
    assert lawsuit.stagnant_since is None


async def test_mover_reseta_stage_entered_at_e_desmarca(factory: LawsuitFactory) -> None:
    stage = await _create_stagnant_stage(factory)
    lawsuit_id = await factory.create("Processo Que Vai Mover", stage_id=stage)
    await _backdate_stage_entered_at(factory, lawsuit_id, _STAGNANT_DAYS + 2)
    await _recalculate_manually(factory)
    assert (await _get_lawsuit(factory, lawsuit_id)).is_stagnant is True

    target_stage = await _create_stage(factory.client, factory.headers, step_id=2)
    response = await factory.client.post(
        f"/api/v1/lawsuits/{lawsuit_id}/move-stage",
        json={"stage_id": target_stage},
        headers=factory.headers,
    )
    assert response.status_code == 200

    lawsuit = await _get_lawsuit(factory, lawsuit_id)
    assert lawsuit.is_stagnant is False
    assert lawsuit.stagnant_since is None


async def test_arquivado_nunca_estagna(factory: LawsuitFactory) -> None:
    stage = await _create_stagnant_stage(factory)
    lawsuit_id = await factory.create("Processo Arquivado", stage_id=stage)
    await _backdate_stage_entered_at(factory, lawsuit_id, _STAGNANT_DAYS + 2)
    await _archive(factory, lawsuit_id)

    await _recalculate_manually(factory)

    lawsuit = await _get_lawsuit(factory, lawsuit_id)
    assert lawsuit.is_stagnant is False
    assert lawsuit.stagnant_since is None


async def test_job_diario_recalcula_o_tenant(factory: LawsuitFactory) -> None:
    """Regra 4 — a varredura diária É `StagnationService.recalculate_tenant`, chamada
    direto (CLAUDE.md §3: teste não toca fila/broker; a task do Celery só orquestra
    sessão + RLS por tenant, sem regra própria)."""
    stage = await _create_stagnant_stage(factory)
    lawsuit_id = await factory.create("Processo Job Diário", stage_id=stage)
    await _backdate_stage_entered_at(factory, lawsuit_id, _STAGNANT_DAYS + 2)

    async with factory.sessions() as session, session.begin():
        await set_tenant_context(session, factory.gestor.tenant_id)
        service = StagnationService(session=session, tenant_id=factory.gestor.tenant_id)
        recalculated = await service.recalculate_tenant()
        assert recalculated >= 1

    lawsuit = await _get_lawsuit(factory, lawsuit_id)
    assert lawsuit.is_stagnant is True


async def test_mudar_stagnant_days_recalcula_a_etapa(factory: LawsuitFactory) -> None:
    """Regra 10 — trocar `stagnant_days` na etapa muda o resultado do PRÓXIMO
    recálculo daquela etapa. O disparo em si é fire-and-forget (`schedule_stage_
    recalculation`, no-op em `app_env=test` — mesmo padrão de `schedule_scores_
    refresh`); aqui provamos a metade que importa: o cálculo reage à config nova."""
    stage = await _create_stagnant_stage(factory, stagnant_days=30)
    lawsuit_id = await factory.create("Processo Limite Alto", stage_id=stage)
    await _backdate_stage_entered_at(factory, lawsuit_id, 10)
    await _recalculate_manually(factory)
    assert (await _get_lawsuit(factory, lawsuit_id)).is_stagnant is False

    update_response = await factory.client.put(
        f"/api/v1/stages/{stage}",
        json={
            "name": "Estagnação Reduzida",
            "step_id": 1,
            "enable_stagnant_days": True,
            "stagnant_days": 3,
        },
        headers=factory.headers,
    )
    assert update_response.status_code == 200

    async with factory.sessions() as session, session.begin():
        await set_tenant_context(session, factory.gestor.tenant_id)
        updated_stage = await StageRepository(session).get_by_id(uuid.UUID(stage))
        assert updated_stage is not None
        service = StagnationService(session=session, tenant_id=factory.gestor.tenant_id)
        await service.recalculate_stage(updated_stage)

    assert (await _get_lawsuit(factory, lawsuit_id)).is_stagnant is True


async def test_filtro_dos_3_modos(factory: LawsuitFactory) -> None:
    stage = await _create_stagnant_stage(factory)
    stagnant_id = await factory.create("Processo Filtro Estagnado", stage_id=stage)
    active_id = await factory.create("Processo Filtro Ativo", stage_id=stage)
    await _backdate_stage_entered_at(factory, stagnant_id, _STAGNANT_DAYS + 2)
    await _recalculate_manually(factory)

    all_response = await factory.client.get(
        "/api/v1/crm/board", params={"display_stagnant": "all"}, headers=factory.headers
    )
    all_ids = {item["id"] for column in all_response.json()["columns"] for item in column["items"]}
    assert {stagnant_id, active_id} <= all_ids

    stagnant_response = await factory.client.get(
        "/api/v1/crm/board", params={"display_stagnant": "stagnant"}, headers=factory.headers
    )
    stagnant_ids = {
        item["id"] for column in stagnant_response.json()["columns"] for item in column["items"]
    }
    assert stagnant_ids == {stagnant_id}

    active_response = await factory.client.get(
        "/api/v1/crm/board", params={"display_stagnant": "active"}, headers=factory.headers
    )
    active_ids = {
        item["id"] for column in active_response.json()["columns"] for item in column["items"]
    }
    assert active_id in active_ids
    assert stagnant_id not in active_ids


async def test_stagnant_value_soma_correto(factory: LawsuitFactory) -> None:
    stage = await _create_stagnant_stage(factory)
    first_id = await factory.create("Processo Valor 1", stage_id=stage, case_value="1000.50")
    second_id = await factory.create("Processo Valor 2", stage_id=stage, case_value="2000.25")
    await _backdate_stage_entered_at(factory, first_id, _STAGNANT_DAYS + 2)
    await _backdate_stage_entered_at(factory, second_id, _STAGNANT_DAYS + 2)
    await _recalculate_manually(factory)

    stats_response = await factory.client.get("/api/v1/crm/stats", headers=factory.headers)
    assert stats_response.status_code == 200
    body = stats_response.json()
    assert body["stagnant_count"] == 2
    assert body["stagnant_value"] == 3000.75


async def test_recalculo_manual_2x_em_1h_da_429(factory: LawsuitFactory) -> None:
    first = await factory.client.post("/api/v1/crm/recalculate-stagnation", headers=factory.headers)
    assert first.status_code == 200

    second = await factory.client.post(
        "/api/v1/crm/recalculate-stagnation", headers=factory.headers
    )
    assert second.status_code == 429
