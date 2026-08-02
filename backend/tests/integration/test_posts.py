import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import _auth_header
from tests.integration.test_lawsuits_listing import LawsuitFactory, _make_factory


@pytest.fixture
async def factory(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> LawsuitFactory:
    return await _make_factory(client, make_user, app_session_factory)


async def _create_task_type(client: AsyncClient, headers: dict[str, str], reward: int = 8) -> str:
    response = await client.post(
        "/api/v1/task-types",
        json={
            "name": f"Tarefa {uuid.uuid4().hex[:8]}",
            "complexity": "SIMPLES",
            "duration": "MIN_15",
            "reward": reward,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return str(response.json()["id"])


async def _create_post(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    lawsuit_id: str,
    task_type_id: str,
    user_ids: list[str] | None = None,
    **extra: object,
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/posts",
        json={
            "lawsuit_id": lawsuit_id,
            "task_type_id": task_type_id,
            "user_ids": user_ids or [],
            "scheduled_date": "2026-08-10",
            **extra,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.json()
    return dict(response.json())


async def test_crud_com_multiplos_responsaveis(
    client: AsyncClient, factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    headers = factory.headers
    segundo = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, headers)

    created = await _create_post(
        client,
        headers,
        lawsuit_id=lawsuit_id,
        task_type_id=task_type_id,
        user_ids=[str(factory.gestor.user_id), str(segundo.user_id)],
        scheduled_time="14:30:00",
        deadline_date="2026-08-05",  # regra 7: prazo fatal pode ser anterior
        location="Fórum Central",
        comments="Levar documentos",
    )
    assert len(created["assignees"]) == 2
    assert created["reward_snapshot"] == 8

    post_id = str(created["id"])
    fetched = await client.get(f"/api/v1/posts/{post_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["location"] == "Fórum Central"

    listed = await client.get(f"/api/v1/lawsuits/{lawsuit_id}/posts", headers=headers)
    assert [item["id"] for item in listed.json()] == [post_id]

    updated = await client.put(
        f"/api/v1/posts/{post_id}",
        json={
            "lawsuit_id": lawsuit_id,
            "task_type_id": task_type_id,
            "user_ids": [str(segundo.user_id)],
            "scheduled_date": "2026-08-12",
            "end_date": "2026-08-12",
            "end_time": "18:00:00",
        },
        headers=headers,
    )
    assert updated.status_code == 200
    assert [a["id"] for a in updated.json()["assignees"]] == [str(segundo.user_id)]

    deleted = await client.delete(f"/api/v1/posts/{post_id}", headers=headers)
    assert deleted.status_code == 204
    assert (await client.get(f"/api/v1/posts/{post_id}", headers=headers)).status_code == 404


async def test_atribuicao_por_time_expande_somente_membros_ativos(
    client: AsyncClient, factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    headers = factory.headers
    ativo = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    inativo = await make_user(
        tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR, is_active=False
    )
    squad = await client.post(
        "/api/v1/squads",
        json={
            "name": f"Time {uuid.uuid4().hex[:6]}",
            "member_ids": [str(ativo.user_id), str(inativo.user_id)],
        },
        headers=headers,
    )
    assert squad.status_code == 201

    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, headers)
    created = await _create_post(
        client,
        headers,
        lawsuit_id=lawsuit_id,
        task_type_id=task_type_id,
        squad_id=str(squad.json()["id"]),
    )
    # Regra 2: expande os ativos no momento da criação — o inativo fica de fora.
    assert [a["id"] for a in created["assignees"]] == [str(ativo.user_id)]


async def test_sem_responsavel_retorna_422(client: AsyncClient, factory: LawsuitFactory) -> None:
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, factory.headers)
    response = await client.post(
        "/api/v1/posts",
        json={"lawsuit_id": lawsuit_id, "task_type_id": task_type_id, "user_ids": []},
        headers=factory.headers,
    )
    assert response.status_code == 422


async def test_duplicata_retorna_409_com_id_existente(
    client: AsyncClient, factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, factory.headers)
    primeiro = await _create_post(
        client,
        factory.headers,
        lawsuit_id=lawsuit_id,
        task_type_id=task_type_id,
        user_ids=[str(factory.gestor.user_id)],
    )

    duplicado = await client.post(
        "/api/v1/posts",
        json={
            "lawsuit_id": lawsuit_id,
            "task_type_id": task_type_id,
            "user_ids": [str(factory.gestor.user_id)],
            "scheduled_date": "2026-08-10",
        },
        headers=factory.headers,
    )
    assert duplicado.status_code == 409
    # Regra 4: o 409 carrega o id da tarefa existente (membro de extensão RFC 7807).
    assert duplicado.json()["existing_id"] == primeiro["id"]

    # Conjunto de responsáveis diferente NÃO é duplicata (regra 4).
    outro = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    nao_duplicado = await client.post(
        "/api/v1/posts",
        json={
            "lawsuit_id": lawsuit_id,
            "task_type_id": task_type_id,
            "user_ids": [str(factory.gestor.user_id), str(outro.user_id)],
            "scheduled_date": "2026-08-10",
        },
        headers=factory.headers,
    )
    assert nao_duplicado.status_code == 201


async def test_end_time_sem_end_date_retorna_422(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, factory.headers)
    response = await client.post(
        "/api/v1/posts",
        json={
            "lawsuit_id": lawsuit_id,
            "task_type_id": task_type_id,
            "user_ids": [str(factory.gestor.user_id)],
            "scheduled_date": "2026-08-10",
            "end_time": "18:00:00",
        },
        headers=factory.headers,
    )
    assert response.status_code == 422


async def test_end_date_anterior_retorna_422(client: AsyncClient, factory: LawsuitFactory) -> None:
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, factory.headers)
    response = await client.post(
        "/api/v1/posts",
        json={
            "lawsuit_id": lawsuit_id,
            "task_type_id": task_type_id,
            "user_ids": [str(factory.gestor.user_id)],
            "scheduled_date": "2026-08-10",
            "end_date": "2026-08-09",
        },
        headers=factory.headers,
    )
    assert response.status_code == 422


async def test_reward_snapshot_congela_na_criacao(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    headers = factory.headers
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, headers, reward=8)
    created = await _create_post(
        client,
        headers,
        lawsuit_id=lawsuit_id,
        task_type_id=task_type_id,
        user_ids=[str(factory.gestor.user_id)],
    )

    # Regra 3: mudar o catálogo depois não reescreve o histórico.
    detalhe = await client.get("/api/v1/task-types", headers=headers)
    tipo = next(item for item in detalhe.json()["items"] if item["id"] == task_type_id)
    await client.put(
        f"/api/v1/task-types/{task_type_id}",
        json={"name": tipo["name"], "reward": 99, "is_active": True},
        headers=headers,
    )

    fetched = await client.get(f"/api/v1/posts/{created['id']}", headers=headers)
    assert fetched.json()["reward_snapshot"] == 8


async def test_excluir_processo_remove_tarefas_no_hard_delete(
    client: AsyncClient, factory: LawsuitFactory, admin_engine: AsyncEngine
) -> None:
    """Regra 8: a FK com ON DELETE CASCADE remove as tarefas junto com o processo —
    testado no hard delete direto no banco (o delete da API é soft desde a 022)."""
    headers = factory.headers
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, headers)
    created = await _create_post(
        client,
        headers,
        lawsuit_id=lawsuit_id,
        task_type_id=task_type_id,
        user_ids=[str(factory.gestor.user_id)],
    )

    # admin_engine é o superusuário (bypassa RLS) — o delete é do banco, sem API.
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM lawsuits WHERE id = CAST(:id AS uuid)"), {"id": lawsuit_id}
        )
        remaining = await conn.execute(
            text("SELECT count(*) FROM posts WHERE id = CAST(:id AS uuid)"),
            {"id": str(created["id"])},
        )
        assert remaining.scalar_one() == 0


async def test_posts_isolados_entre_tenants(
    client: AsyncClient, factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, factory.headers)
    created = await _create_post(
        client,
        factory.headers,
        lawsuit_id=lawsuit_id,
        task_type_id=task_type_id,
        user_ids=[str(factory.gestor.user_id)],
    )

    outro_gestor = await make_user(role=UserRole.GESTOR)
    headers_b = _auth_header(outro_gestor)
    resposta_b = await client.get(f"/api/v1/posts/{created['id']}", headers=headers_b)
    assert resposta_b.status_code == 404
    assert (
        await client.get(f"/api/v1/lawsuits/{lawsuit_id}/posts", headers=headers_b)
    ).json() == []


async def test_tipo_em_uso_exige_transferencia(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 5 da spec 031, plugada agora que `posts` existe: excluir tipo em uso →
    409; transferindo antes, a exclusão libera."""
    headers = factory.headers
    lawsuit_id = await factory.create()
    tipo_em_uso = await _create_task_type(client, headers)
    tipo_destino = await _create_task_type(client, headers)
    await _create_post(
        client,
        headers,
        lawsuit_id=lawsuit_id,
        task_type_id=tipo_em_uso,
        user_ids=[str(factory.gestor.user_id)],
    )

    bloqueado = await client.delete(f"/api/v1/task-types/{tipo_em_uso}", headers=headers)
    assert bloqueado.status_code == 409

    transferido = await client.post(
        "/api/v1/task-types/transfer",
        json={"from_id": tipo_em_uso, "to_id": tipo_destino},
        headers=headers,
    )
    assert transferido.json() == {"transferred_count": 1}

    liberado = await client.delete(f"/api/v1/task-types/{tipo_em_uso}", headers=headers)
    assert liberado.status_code == 204
