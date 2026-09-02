"""Spec 038 — workflow: CRUD com reconcile, preview, aplicação transacional e
isolamento entre tenants.

Cobre as regras 1–2 (etapa exige tipo; responsável nulo herda o do processo), 3–4
(datas em dias úteis), 5 (aplicação transacional), 6 (preview não persiste), 8
(reaplicar exige confirmação), 9 (excluir não apaga tarefas), 10 (tipo inativo é
pulado com aviso) e o RBAC da escrita (GESTOR).
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.users.models import UserRole
from app.domain.workflows.business_days import add_business_days
from tests.clock import hoje
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import _auth_header
from tests.integration.test_lawsuits_listing import LawsuitFactory, _make_factory
from tests.integration.test_posts import _create_task_type

_TODAY = hoje()


@pytest.fixture
async def factory(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> LawsuitFactory:
    return await _make_factory(client, make_user, app_session_factory)


async def _create_workflow(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    name: str | None = None,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/workflows",
        json={"name": name or f"Fluxo {uuid.uuid4().hex[:8]}", "steps": steps},
        headers=headers,
    )
    assert response.status_code == 201, response.json()
    return dict(response.json())


async def _lawsuit_post_ids(
    client: AsyncClient, headers: dict[str, str], lawsuit_id: str
) -> list[dict[str, Any]]:
    response = await client.get(f"/api/v1/lawsuits/{lawsuit_id}/posts", headers=headers)
    assert response.status_code == 200, response.json()
    body = response.json()
    items = body["items"] if isinstance(body, dict) else body
    return list(items)


async def _national_holidays(client: AsyncClient, headers: dict[str, str]) -> set[date]:
    response = await client.get("/api/v1/holidays", headers=headers)
    assert response.status_code == 200
    return {date.fromisoformat(item["date"]) for item in response.json()["items"]}


async def test_crud_com_etapas_reconciliadas(client: AsyncClient, factory: LawsuitFactory) -> None:
    headers = factory.headers
    tipo_a = await _create_task_type(client, headers)
    tipo_b = await _create_task_type(client, headers)
    tipo_c = await _create_task_type(client, headers)

    created = await _create_workflow(
        client,
        headers,
        steps=[
            {"task_type_id": tipo_a, "days_offset": 0},
            {"task_type_id": tipo_b, "days_offset": 2},
            {"task_type_id": tipo_c},
        ],
    )
    assert [step["task_type_id"] for step in created["steps"]] == [tipo_a, tipo_b, tipo_c]

    # PUT reconcilia o conjunto inteiro: ordem nova (B, A) e C removido (regra 11).
    response = await client.put(
        f"/api/v1/workflows/{created['id']}",
        json={
            "name": created["name"],
            "steps": [
                {"task_type_id": tipo_b, "days_offset": 5},
                {"task_type_id": tipo_a, "days_offset": 1},
            ],
        },
        headers=headers,
    )
    assert response.status_code == 200, response.json()
    updated = response.json()
    assert [step["task_type_id"] for step in updated["steps"]] == [tipo_b, tipo_a]
    assert updated["steps"][0]["days_offset"] == 5

    detail = await client.get(f"/api/v1/workflows/{created['id']}", headers=headers)
    assert [step["task_type_id"] for step in detail.json()["steps"]] == [tipo_b, tipo_a]


async def test_aplicar_cria_n_tarefas_com_datas_certas(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    headers = factory.headers
    lawsuit_id = await factory.create()
    tipo_a = await _create_task_type(client, headers)
    tipo_b = await _create_task_type(client, headers)
    tipo_c = await _create_task_type(client, headers)
    workflow = await _create_workflow(
        client,
        headers,
        steps=[
            {"task_type_id": tipo_a, "days_offset": 0},
            {"task_type_id": tipo_b, "days_offset": 3},
            {"task_type_id": tipo_c},  # regra 4: nulo = sem prazo
        ],
    )

    response = await client.post(
        f"/api/v1/workflows/{workflow['id']}/apply",
        json={"lawsuit_id": lawsuit_id},
        headers=headers,
    )
    assert response.status_code == 200, response.json()
    assert response.json()["created"] == 3

    holidays = await _national_holidays(client, headers)
    posts = await _lawsuit_post_ids(client, headers, lawsuit_id)
    by_type = {post["task_type_id"]: post for post in posts}
    assert by_type[tipo_a]["scheduled_date"] == _TODAY.isoformat()
    assert by_type[tipo_b]["scheduled_date"] == add_business_days(_TODAY, 3, holidays).isoformat()
    assert by_type[tipo_c]["scheduled_date"] is None


async def test_responsavel_nulo_herda_o_do_processo(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    headers = factory.headers
    lawsuit_id = await factory.create()
    tipo = await _create_task_type(client, headers)
    workflow = await _create_workflow(client, headers, steps=[{"task_type_id": tipo}])

    await client.post(
        f"/api/v1/workflows/{workflow['id']}/apply",
        json={"lawsuit_id": lawsuit_id},
        headers=headers,
    )
    posts = await _lawsuit_post_ids(client, headers, lawsuit_id)
    (post,) = posts
    assert [a["id"] for a in post["assignees"]] == [str(factory.gestor.user_id)]


async def test_aplicacao_e_transacional(
    client: AsyncClient,
    factory: LawsuitFactory,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    headers = factory.headers
    lawsuit_id = await factory.create()
    tipo_a = await _create_task_type(client, headers)
    tipo_b = await _create_task_type(client, headers)
    # O responsável da 2ª etapa NASCE inativo (spec 012: inativo não recebe tarefa) —
    # regra 5: falha no meio, NENHUMA tarefa é criada.
    inativo = await make_user(
        tenant_id=factory.gestor.tenant_id, is_active=False, role=UserRole.COLABORADOR
    )
    workflow = await _create_workflow(
        client,
        headers,
        steps=[{"task_type_id": tipo_a}, {"task_type_id": tipo_b, "user_id": str(inativo.user_id)}],
    )

    response = await client.post(
        f"/api/v1/workflows/{workflow['id']}/apply",
        json={"lawsuit_id": lawsuit_id},
        headers=headers,
    )
    assert response.status_code == 422
    assert await _lawsuit_post_ids(client, headers, lawsuit_id) == []


async def test_preview_nao_persiste(client: AsyncClient, factory: LawsuitFactory) -> None:
    headers = factory.headers
    lawsuit_id = await factory.create()
    tipo = await _create_task_type(client, headers)
    workflow = await _create_workflow(
        client, headers, steps=[{"task_type_id": tipo, "days_offset": 1}]
    )

    response = await client.post(
        f"/api/v1/workflows/{workflow['id']}/preview",
        json={"lawsuit_id": lawsuit_id},
        headers=headers,
    )
    assert response.status_code == 200, response.json()
    assert len(response.json()["tasks"]) == 1
    # Regra 6: o preview mostra exatamente o que seria criado, sem gravar nada.
    assert await _lawsuit_post_ids(client, headers, lawsuit_id) == []


async def test_tipo_inativo_e_pulado_com_aviso(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    headers = factory.headers
    lawsuit_id = await factory.create()
    tipo_ativo = await _create_task_type(client, headers)
    tipo_inativo = await _create_task_type(client, headers)
    update = await client.put(
        f"/api/v1/task-types/{tipo_inativo}",
        json={"name": f"Inativo {uuid.uuid4().hex[:8]}", "reward": 0, "is_active": False},
        headers=headers,
    )
    assert update.status_code == 200, update.json()
    workflow = await _create_workflow(
        client,
        headers,
        steps=[{"task_type_id": tipo_ativo}, {"task_type_id": tipo_inativo}],
    )

    response = await client.post(
        f"/api/v1/workflows/{workflow['id']}/apply",
        json={"lawsuit_id": lawsuit_id},
        headers=headers,
    )
    assert response.status_code == 200, response.json()
    body = response.json()
    # Regra 10: o inativo é pulado COM AVISO, o ativo é criado normalmente.
    assert body["created"] == 1
    assert len(body["skipped"]) == 1
    assert "inativo" in body["skipped"][0]["reason"].lower()


async def test_excluir_workflow_nao_apaga_tarefas(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    headers = factory.headers
    lawsuit_id = await factory.create()
    tipo = await _create_task_type(client, headers)
    workflow = await _create_workflow(client, headers, steps=[{"task_type_id": tipo}])
    await client.post(
        f"/api/v1/workflows/{workflow['id']}/apply",
        json={"lawsuit_id": lawsuit_id},
        headers=headers,
    )

    delete = await client.delete(f"/api/v1/workflows/{workflow['id']}", headers=headers)
    assert delete.status_code == 204
    # Regra 9: as tarefas criadas sobrevivem à exclusão do workflow.
    assert len(await _lawsuit_post_ids(client, headers, lawsuit_id)) == 1


async def test_reaplicar_exige_confirmacao(client: AsyncClient, factory: LawsuitFactory) -> None:
    headers = factory.headers
    lawsuit_id = await factory.create()
    tipo = await _create_task_type(client, headers)
    workflow = await _create_workflow(client, headers, steps=[{"task_type_id": tipo}])
    await client.post(
        f"/api/v1/workflows/{workflow['id']}/apply",
        json={"lawsuit_id": lawsuit_id},
        headers=headers,
    )

    # Regra 8: sem confirm_duplicate → 409; com → cria de novo.
    denovo = await client.post(
        f"/api/v1/workflows/{workflow['id']}/apply",
        json={"lawsuit_id": lawsuit_id},
        headers=headers,
    )
    assert denovo.status_code == 409
    confirmado = await client.post(
        f"/api/v1/workflows/{workflow['id']}/apply",
        json={"lawsuit_id": lawsuit_id, "confirm_duplicate": True},
        headers=headers,
    )
    assert confirmado.status_code == 200, confirmado.json()
    assert len(await _lawsuit_post_ids(client, headers, lawsuit_id)) == 2


async def test_colaborador_nao_cria_workflow(
    client: AsyncClient,
    factory: LawsuitFactory,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    colaborador = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    tipo = await _create_task_type(client, factory.headers)
    response = await client.post(
        "/api/v1/workflows",
        json={"name": f"Fluxo {uuid.uuid4().hex[:8]}", "steps": [{"task_type_id": tipo}]},
        headers=_auth_header(colaborador),
    )
    assert response.status_code == 403


async def test_tenant_b_nao_enxerga_workflow_de_a(
    client: AsyncClient,
    factory: LawsuitFactory,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    tenant_b_gestor = await make_user(role=UserRole.GESTOR)
    tipo = await _create_task_type(client, factory.headers)
    workflow = await _create_workflow(client, factory.headers, steps=[{"task_type_id": tipo}])

    headers_b = _auth_header(tenant_b_gestor)
    lista = await client.get("/api/v1/workflows", headers=headers_b)
    assert lista.status_code == 200
    assert lista.json()["items"] == []
    detalhe = await client.get(f"/api/v1/workflows/{workflow['id']}", headers=headers_b)
    assert detalhe.status_code == 404
