import uuid
from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import _auth_header


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
