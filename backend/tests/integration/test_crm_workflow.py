"""CRM: workflow ao mover (spec 053, §8) — sugestão ao mover, aplicação registrada,
transacionalidade, desfazer (janela de 1h e tarefa concluída), supressão, reaplicar
com confirmação e ação em massa nunca sugere."""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import text

from app.core.rls import set_tenant_context
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import _auth_header, _create_stage
from tests.integration.test_lawsuits_listing import LawsuitFactory
from tests.integration.test_lawsuits_listing import factory as factory
from tests.integration.test_posts import _create_task_type
from tests.integration.test_workflows import _create_workflow, _lawsuit_post_ids

_NEGOTIATION_STEP_ID = 2


async def _create_stage_with_workflow(
    factory: LawsuitFactory, workflow_id: str, *, step_id: int = _NEGOTIATION_STEP_ID
) -> str:
    suffix = uuid.uuid4().hex[:8]
    response = await factory.client.post(
        "/api/v1/stages",
        json={"name": f"Etapa {suffix}", "step_id": step_id, "suggested_workflow_id": workflow_id},
        headers=factory.headers,
    )
    assert response.status_code == 201, response.text
    result: str = response.json()["id"]
    return result


async def _move(factory: LawsuitFactory, lawsuit_id: str, stage_id: str) -> dict[str, Any]:
    response = await factory.client.post(
        f"/api/v1/lawsuits/{lawsuit_id}/move-stage",
        json={"stage_id": stage_id},
        headers=factory.headers,
    )
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


async def _apply(
    factory: LawsuitFactory,
    lawsuit_id: str,
    workflow_id: str,
    *,
    stage_id: str | None = None,
    confirm_duplicate: bool = False,
) -> Any:
    payload: dict[str, Any] = {"workflow_id": workflow_id, "confirm_duplicate": confirm_duplicate}
    if stage_id is not None:
        payload["stage_id"] = stage_id
    return await factory.client.post(
        f"/api/v1/lawsuits/{lawsuit_id}/apply-workflow", json=payload, headers=factory.headers
    )


async def _applications(factory: LawsuitFactory, lawsuit_id: str) -> list[dict[str, Any]]:
    response = await factory.client.get(
        f"/api/v1/lawsuits/{lawsuit_id}/workflow-applications", headers=factory.headers
    )
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


async def _complete_post(client: AsyncClient, headers: dict[str, str], post_id: str) -> None:
    response = await client.post(f"/api/v1/posts/{post_id}/complete", json={}, headers=headers)
    assert response.status_code == 200, response.text


async def _backdate_application(
    factory: LawsuitFactory, application_id: str, applied_at: datetime
) -> None:
    async with factory.sessions() as session, session.begin():
        await set_tenant_context(session, factory.gestor.tenant_id)
        await session.execute(
            text("UPDATE workflow_applications SET applied_at = :ts WHERE id = CAST(:id AS uuid)"),
            {"ts": applied_at, "id": application_id},
        )


async def test_mover_sugere_o_workflow_da_etapa(factory: LawsuitFactory) -> None:
    tipo = await _create_task_type(factory.client, factory.headers)
    workflow = await _create_workflow(
        factory.client, factory.headers, steps=[{"task_type_id": tipo}]
    )
    target_stage = await _create_stage_with_workflow(factory, workflow["id"])
    lawsuit_id = await factory.create("Processo Sugestão")

    moved = await _move(factory, lawsuit_id, target_stage)

    assert moved["suggested_workflow"] is not None
    assert moved["suggested_workflow"]["id"] == workflow["id"]
    assert moved["lawsuit"]["stage_id"] == target_stage


async def test_etapa_sem_workflow_nao_sugere(factory: LawsuitFactory) -> None:
    target_stage = await _create_stage(
        factory.client, factory.headers, step_id=_NEGOTIATION_STEP_ID
    )
    lawsuit_id = await factory.create("Processo Sem Sugestão")

    moved = await _move(factory, lawsuit_id, target_stage)

    assert moved["suggested_workflow"] is None


async def test_aplicar_cria_as_tarefas_e_registra(factory: LawsuitFactory) -> None:
    lawsuit_id = await factory.create("Processo Aplicar")
    tipo_a = await _create_task_type(factory.client, factory.headers)
    tipo_b = await _create_task_type(factory.client, factory.headers)
    workflow = await _create_workflow(
        factory.client, factory.headers, steps=[{"task_type_id": tipo_a}, {"task_type_id": tipo_b}]
    )

    response = await _apply(factory, lawsuit_id, workflow["id"], stage_id=factory.stage_id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 2
    assert len(body["post_ids"]) == 2

    applications = await _applications(factory, lawsuit_id)
    assert len(applications) == 1
    assert applications[0]["workflow_id"] == workflow["id"]
    assert applications[0]["stage_id"] == factory.stage_id
    assert sorted(applications[0]["posts_created"]) == sorted(body["post_ids"])


async def test_aplicacao_e_transacional(
    factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    lawsuit_id = await factory.create("Processo Transacional")
    tipo_a = await _create_task_type(factory.client, factory.headers)
    tipo_b = await _create_task_type(factory.client, factory.headers)
    inativo = await make_user(
        tenant_id=factory.gestor.tenant_id, is_active=False, role=UserRole.COLABORADOR
    )
    workflow = await _create_workflow(
        factory.client,
        factory.headers,
        steps=[
            {"task_type_id": tipo_a},
            {"task_type_id": tipo_b, "user_id": str(inativo.user_id)},
        ],
    )

    response = await _apply(factory, lawsuit_id, workflow["id"])
    assert response.status_code == 422
    assert await _lawsuit_post_ids(factory.client, factory.headers, lawsuit_id) == []
    assert await _applications(factory, lawsuit_id) == []


async def test_desfazer_em_1h_remove_as_tarefas(factory: LawsuitFactory) -> None:
    lawsuit_id = await factory.create("Processo Desfazer")
    tipo = await _create_task_type(factory.client, factory.headers)
    workflow = await _create_workflow(
        factory.client, factory.headers, steps=[{"task_type_id": tipo}]
    )
    applied = await _apply(factory, lawsuit_id, workflow["id"])
    application_id = applied.json()["application_id"]

    undo = await factory.client.delete(
        f"/api/v1/lawsuits/{lawsuit_id}/workflow-applications/{application_id}",
        headers=factory.headers,
    )
    assert undo.status_code == 204
    assert await _lawsuit_post_ids(factory.client, factory.headers, lawsuit_id) == []
    assert await _applications(factory, lawsuit_id) == []


async def test_desfazer_com_tarefa_concluida_da_409(factory: LawsuitFactory) -> None:
    lawsuit_id = await factory.create("Processo Concluído")
    tipo = await _create_task_type(factory.client, factory.headers)
    workflow = await _create_workflow(
        factory.client, factory.headers, steps=[{"task_type_id": tipo}]
    )
    applied = await _apply(factory, lawsuit_id, workflow["id"])
    body = applied.json()
    await _complete_post(factory.client, factory.headers, body["post_ids"][0])

    undo = await factory.client.delete(
        f"/api/v1/lawsuits/{lawsuit_id}/workflow-applications/{body['application_id']}",
        headers=factory.headers,
    )
    assert undo.status_code == 409


async def test_desfazer_apos_1h_da_409(factory: LawsuitFactory) -> None:
    lawsuit_id = await factory.create("Processo Expirado")
    tipo = await _create_task_type(factory.client, factory.headers)
    workflow = await _create_workflow(
        factory.client, factory.headers, steps=[{"task_type_id": tipo}]
    )
    applied = await _apply(factory, lawsuit_id, workflow["id"])
    application_id = applied.json()["application_id"]
    await _backdate_application(factory, application_id, datetime.now(UTC) - timedelta(hours=2))

    undo = await factory.client.delete(
        f"/api/v1/lawsuits/{lawsuit_id}/workflow-applications/{application_id}",
        headers=factory.headers,
    )
    assert undo.status_code == 409


async def test_supressao_impede_nova_sugestao(factory: LawsuitFactory) -> None:
    tipo = await _create_task_type(factory.client, factory.headers)
    workflow = await _create_workflow(
        factory.client, factory.headers, steps=[{"task_type_id": tipo}]
    )
    target_stage = await _create_stage_with_workflow(factory, workflow["id"])
    other_stage = await _create_stage(factory.client, factory.headers, step_id=_NEGOTIATION_STEP_ID)
    lawsuit_id = await factory.create("Processo Supressão")

    first_move = await _move(factory, lawsuit_id, target_stage)
    assert first_move["suggested_workflow"] is not None

    suppress = await factory.client.post(
        f"/api/v1/lawsuits/{lawsuit_id}/suppress-workflow",
        json={"stage_id": target_stage},
        headers=factory.headers,
    )
    assert suppress.status_code == 204

    await _move(factory, lawsuit_id, other_stage)
    second_move = await _move(factory, lawsuit_id, target_stage)
    assert second_move["suggested_workflow"] is None


async def test_reaplicar_pede_confirmacao(factory: LawsuitFactory) -> None:
    lawsuit_id = await factory.create("Processo Reaplicar")
    tipo = await _create_task_type(factory.client, factory.headers)
    workflow = await _create_workflow(
        factory.client, factory.headers, steps=[{"task_type_id": tipo}]
    )
    await _apply(factory, lawsuit_id, workflow["id"])

    denovo = await _apply(factory, lawsuit_id, workflow["id"])
    assert denovo.status_code == 409
    assert "aplicado" in denovo.json()["detail"].lower()

    confirmado = await _apply(factory, lawsuit_id, workflow["id"], confirm_duplicate=True)
    assert confirmado.status_code == 200, confirmado.text
    assert len(await _lawsuit_post_ids(factory.client, factory.headers, lawsuit_id)) == 2
    assert len(await _applications(factory, lawsuit_id)) == 2


async def test_movimento_em_massa_nao_sugere(factory: LawsuitFactory) -> None:
    tipo = await _create_task_type(factory.client, factory.headers)
    workflow = await _create_workflow(
        factory.client, factory.headers, steps=[{"task_type_id": tipo}]
    )
    target_stage = await _create_stage_with_workflow(factory, workflow["id"])
    lawsuit_id = await factory.create("Processo Massa")

    response = await factory.client.post(
        "/api/v1/lawsuits/bulk/move-stage",
        json={"lawsuit_ids": [lawsuit_id], "stage_id": target_stage},
        headers=factory.headers,
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"moved": 1}
    assert "suggested_workflow" not in response.json()


async def test_tenant_b_nao_enxerga_aplicacoes_de_a(
    factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """CLAUDE.md §4: tenant A não enxerga dado de tenant B — `workflow_applications`/
    `workflow_suppressions` são tabelas novas nesta spec."""
    lawsuit_id = await factory.create("Processo Isolamento")
    tipo = await _create_task_type(factory.client, factory.headers)
    workflow = await _create_workflow(
        factory.client, factory.headers, steps=[{"task_type_id": tipo}]
    )
    await _apply(factory, lawsuit_id, workflow["id"])

    tenant_b_gestor = await make_user(role=UserRole.GESTOR)
    headers_b = _auth_header(tenant_b_gestor)

    applications = await factory.client.get(
        f"/api/v1/lawsuits/{lawsuit_id}/workflow-applications", headers=headers_b
    )
    assert applications.status_code == 404

    suppress = await factory.client.post(
        f"/api/v1/lawsuits/{lawsuit_id}/suppress-workflow",
        json={"stage_id": factory.stage_id},
        headers=headers_b,
    )
    assert suppress.status_code == 404
