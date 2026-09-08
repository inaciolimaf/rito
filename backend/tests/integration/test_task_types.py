import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.users.models import UserRole
from app.main import app
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import _auth_header
from tests.integration.test_lawsuits_listing import LawsuitFactory, _make_factory
from tests.integration.test_posts import _create_post, _create_task_type
from tests.perf import query_budget


@pytest.fixture
async def factory(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> LawsuitFactory:
    return await _make_factory(client, make_user, app_session_factory)


@pytest.fixture
async def gestor(make_user: Callable[..., Awaitable[SeededUser]]) -> SeededUser:
    return await make_user(role=UserRole.GESTOR)


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": f"Tarefa {uuid.uuid4().hex[:8]}",
        "complexity": "SIMPLES",
        "duration": "MIN_15",
        "reward": None,
        "show_in_schedule": False,
    }
    base.update(overrides)
    return base


async def test_crud_completo(client: AsyncClient, gestor: SeededUser) -> None:
    headers = _auth_header(gestor)

    # Sugestão da matriz quando reward não é informado (regra 2): SIMPLES×15min = 8.
    created = await client.post("/api/v1/task-types", json=_payload(), headers=headers)
    assert created.status_code == 201
    body = created.json()
    assert body["reward"] == 8
    assert body["step_name"] is None  # sem fase = todas (regra 3)
    assert body["is_system"] is False

    # Valor informado vence a sugestão (regra 2).
    custom = await client.post("/api/v1/task-types", json=_payload(reward=42), headers=headers)
    assert custom.json()["reward"] == 42

    listed = await client.get("/api/v1/task-types", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 2

    updated = await client.put(
        f"/api/v1/task-types/{body['id']}",
        json={**_payload(name=body["name"], reward=10, is_active=False)},
        headers=headers,
    )
    assert updated.status_code == 200
    # Regra 6: inativar é flag, o registro continua listável como inativo.
    assert updated.json()["is_active"] is False
    inativos = await client.get(
        "/api/v1/task-types", params={"status": "inactive"}, headers=headers
    )
    assert inativos.json()["total"] == 1

    deleted = await client.delete(f"/api/v1/task-types/{body['id']}", headers=headers)
    assert deleted.status_code == 204


async def test_administrador_nao_escreve_no_catalogo(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    # Regra 1: só GESTOR escreve; Administrador e Colaborador só leem.
    admin = await make_user(role=UserRole.ADMINISTRADOR)
    headers = _auth_header(admin)

    escrita = await client.post("/api/v1/task-types", json=_payload(), headers=headers)
    assert escrita.status_code == 403
    leitura = await client.get("/api/v1/task-types", headers=headers)
    assert leitura.status_code == 200


async def test_sistemica_nao_exclui_nem_renomeia_mas_muda_pontuacao(
    client: AsyncClient,
    gestor: SeededUser,
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    headers = _auth_header(gestor)
    # A seed da migration só atinge tenants pré-migration — a sistêmica do teste
    # (regra 4) nasce via SQL no tenant dele.
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, gestor.tenant_id)
        await session.execute(
            text(
                "INSERT INTO task_types (tenant_id, name, reward, is_system) "
                "VALUES (:tenant, 'Intimações Judiciais', 0, true)"
            ),
            {"tenant": gestor.tenant_id},
        )

    listed = await client.get("/api/v1/task-types", headers=headers)
    (sistemica,) = [item for item in listed.json()["items"] if item["is_system"]]

    excluir = await client.delete(f"/api/v1/task-types/{sistemica['id']}", headers=headers)
    assert excluir.status_code == 403

    renomear = await client.put(
        f"/api/v1/task-types/{sistemica['id']}",
        json=_payload(name="Outro Nome", reward=0),
        headers=headers,
    )
    assert renomear.status_code == 403

    # Regra 4: só a pontuação muda — permitido.
    pontuar = await client.put(
        f"/api/v1/task-types/{sistemica['id']}",
        json=_payload(name="Intimações Judiciais", reward=15),
        headers=headers,
    )
    assert pontuar.status_code == 200
    assert pontuar.json()["reward"] == 15


async def test_reward_negativo_retorna_422(client: AsyncClient, gestor: SeededUser) -> None:
    response = await client.post(
        "/api/v1/task-types", json=_payload(reward=-1), headers=_auth_header(gestor)
    )
    assert response.status_code == 422


async def test_transfer_valida_ids_e_exclui_depois(client: AsyncClient, gestor: SeededUser) -> None:
    headers = _auth_header(gestor)
    origem = (await client.post("/api/v1/task-types", json=_payload(), headers=headers)).json()
    destino = (await client.post("/api/v1/task-types", json=_payload(), headers=headers)).json()

    mesmo = await client.post(
        "/api/v1/task-types/transfer",
        json={"from_id": origem["id"], "to_id": origem["id"]},
        headers=headers,
    )
    assert mesmo.status_code == 422

    inexistente = await client.post(
        "/api/v1/task-types/transfer",
        json={"from_id": origem["id"], "to_id": str(uuid.uuid4())},
        headers=headers,
    )
    assert inexistente.status_code == 422

    # Sem `tasks` até a 032, transferir reatribui 0 registros — e a exclusão libera.
    transferido = await client.post(
        "/api/v1/task-types/transfer",
        json={"from_id": origem["id"], "to_id": destino["id"]},
        headers=headers,
    )
    assert transferido.status_code == 200
    assert transferido.json() == {"transferred_count": 0}
    excluir = await client.delete(f"/api/v1/task-types/{origem['id']}", headers=headers)
    assert excluir.status_code == 204


async def test_tipos_isolados_entre_tenants(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor_a = await make_user(role=UserRole.GESTOR)
    await client.post("/api/v1/task-types", json=_payload(), headers=_auth_header(gestor_a))

    gestor_b = await make_user(role=UserRole.GESTOR)
    listed = await client.get("/api/v1/task-types", headers=_auth_header(gestor_b))
    assert listed.json()["items"] == []


# --------------------------------------------------------------------------------------
# Spec 125 — "última atribuição" (regra 9 da 031), que era um `None` literal no router.
# --------------------------------------------------------------------------------------


def _por_id(corpo: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = corpo["items"]
    assert isinstance(items, list)
    return {str(item["id"]): dict(item) for item in items}


async def _listar_sem_cache(client: AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    """A listagem pelo caminho FILTRADO, de propósito.

    A chamada sem filtro é cacheada por 5 minutos (spec 098, regra 9) e a invalidação por
    evento só dispara em escrita de CATÁLOGO — criar tarefa não derruba a chave. Um teste
    que medisse por ali estaria afirmando sobre o Redis, não sobre o cálculo.
    """
    resposta = await client.get("/api/v1/task-types", params={"status": "active"}, headers=headers)
    assert resposta.status_code == 200
    return dict(resposta.json())


async def test_ultima_atribuicao_deriva_das_tarefas(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    headers = factory.headers
    lawsuit_id = await factory.create()
    usado = await _create_task_type(client, headers)
    nunca_usado = await _create_task_type(client, headers)

    # (a) Tipo sem tarefa nenhuma: null significa "nunca atribuído".
    antes = _por_id(await _listar_sem_cache(client, headers))
    assert antes[usado]["last_assigned_at"] is None
    assert antes[nunca_usado]["last_assigned_at"] is None

    tarefa = await _create_post(
        client,
        headers,
        lawsuit_id=lawsuit_id,
        task_type_id=usado,
        user_ids=[str(factory.gestor.user_id)],
    )

    # (b) A data é a da criação da tarefa, e só o tipo atribuído muda.
    depois = _por_id(await _listar_sem_cache(client, headers))
    assert depois[usado]["last_assigned_at"] == tarefa["created_at"]
    assert depois[nunca_usado]["last_assigned_at"] is None


async def test_ultima_atribuicao_e_a_mais_recente_e_bate_com_o_detalhe(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    headers = factory.headers
    lawsuit_id = await factory.create()
    tipo = await _create_task_type(client, headers)

    primeira = await _create_post(
        client,
        headers,
        lawsuit_id=lawsuit_id,
        task_type_id=tipo,
        user_ids=[str(factory.gestor.user_id)],
    )
    # Data diferente porque tarefa igual em processo/tipo/data/responsável é 409 (032).
    segunda = await _create_post(
        client,
        headers,
        lawsuit_id=lawsuit_id,
        task_type_id=tipo,
        user_ids=[str(factory.gestor.user_id)],
        scheduled_date="2026-08-11",
    )
    assert segunda["created_at"] > primeira["created_at"]

    # É um MAX: a mais recente vence, não a primeira nem a contagem.
    listagem = _por_id(await _listar_sem_cache(client, headers))
    assert listagem[tipo]["last_assigned_at"] == segunda["created_at"]

    # (c) O PUT — o "detalhe" deste recurso, que não tem GET por id — concorda com a
    # listagem. Foram os dois caminhos discordando (um calculado, outro constante) que
    # produziram a dívida 25.
    detalhe = await client.put(
        f"/api/v1/task-types/{tipo}",
        json=_payload(name=f"Tarefa {uuid.uuid4().hex[:8]}", reward=9),
        headers=headers,
    )
    assert detalhe.status_code == 200
    assert detalhe.json()["last_assigned_at"] == segunda["created_at"]

    # E o POST, num tipo que acabou de nascer, devolve o null de "nunca atribuído".
    criado = await client.post("/api/v1/task-types", json=_payload(), headers=headers)
    assert criado.json()["last_assigned_at"] is None


async def test_listagem_de_tipos_cabe_em_tres_queries(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """CLAUDE.md §11: listagem em 3 statements — usuário do token, catálogo, fases.

    Medido no caminho FILTRADO pelo mesmo motivo do helper acima: pelo cacheado o
    orçamento daria 1 e uma query por linha passaria despercebida, que é exatamente a
    regressão que este gate existe para pegar.
    """
    headers = factory.headers
    lawsuit_id = await factory.create()
    for _ in range(3):
        tipo = await _create_task_type(client, headers)
        await _create_post(
            client,
            headers,
            lawsuit_id=lawsuit_id,
            task_type_id=tipo,
            user_ids=[str(factory.gestor.user_id)],
        )

    async with query_budget(app, 3, label="listagem de tipos de tarefa"):
        resposta = await client.get(
            "/api/v1/task-types", params={"status": "active"}, headers=headers
        )
    assert resposta.status_code == 200
    assert len(resposta.json()["items"]) == 3


async def test_ultima_atribuicao_nao_atravessa_tenant(
    client: AsyncClient,
    factory: LawsuitFactory,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """RLS (CLAUDE.md §4): a derivada é um `MAX` sobre `posts`, e ninguém filtra tenant no
    `WHERE` — quem escopa é a política.

    O escritório vizinho cria a tarefa DEPOIS, então a data dele é maior: se a política
    falhasse, ela é que apareceria aqui. É a forma de o teste morder de verdade, em vez de
    conferir uma listagem vazia (isso já é `test_tipos_isolados_entre_tenants`).
    """
    tipo_a = await _create_task_type(client, factory.headers)
    tarefa_a = await _create_post(
        client,
        factory.headers,
        lawsuit_id=await factory.create(),
        task_type_id=tipo_a,
        user_ids=[str(factory.gestor.user_id)],
    )

    vizinho = await _make_factory(client, make_user, app_session_factory)
    tipo_b = await _create_task_type(client, vizinho.headers)
    tarefa_b = await _create_post(
        client,
        vizinho.headers,
        lawsuit_id=await vizinho.create(),
        task_type_id=tipo_b,
        user_ids=[str(vizinho.gestor.user_id)],
    )
    assert tarefa_b["created_at"] > tarefa_a["created_at"]

    assert (
        _por_id(await _listar_sem_cache(client, factory.headers))[tipo_a]["last_assigned_at"]
        == tarefa_a["created_at"]
    )
    assert (
        _por_id(await _listar_sem_cache(client, vizinho.headers))[tipo_b]["last_assigned_at"]
        == tarefa_b["created_at"]
    )
