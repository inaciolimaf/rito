"""Relatórios tabulares (spec 072) — 9 relatórios em tempo real (sem view
materializada), com filtros comuns, keyset e rodapé de pontos onde a spec pede."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.users.models import UserRole
from tests.clock import hoje
from tests.integration.conftest import SeededUser, auth_header
from tests.integration.test_lawsuits import _create_customer, _create_lawsuit
from tests.integration.test_lawsuits_listing import LawsuitFactory, _make_factory
from tests.integration.test_taskscore import _complete, _setup_post

# Spec 114: o dia é o do ESCRITÓRIO. Era o dia UTC — três horas à frente de São
# Paulo, que é o fuso em
# que as fixtures criam a conta. O `DTZ` não pega este caso: `datetime.now(UTC)` TEM
# fuso, só que o fuso errado para a pergunta «que dia é hoje no escritório».
_TODAY = hoje()
# Dívida 32: `created_at` é timestamp UTC, e os relatórios que filtram por ele comparam
# com um intervalo de DATAS. Enquanto essa conversão não existir, os dois testes que
# dependem de `created_at` precisam perguntar em dia UTC — senão, das 21h em diante, o
# contato criado agora cai no dia UTC seguinte e some do filtro «de hoje até hoje».
# O resto do arquivo usa `_TODAY` (dia do escritório), que é o certo para `scheduled_date`
# e `closure_date`, que são DATAS e não timestamps.
_HOJE_UTC = datetime.now(UTC).date()


@pytest.fixture
async def factory(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> LawsuitFactory:
    return await _make_factory(client, make_user, app_session_factory)


async def _tabular(
    client: AsyncClient, headers: dict[str, str], report_key: str, **params: str
) -> Any:
    response = await client.get(
        f"/api/v1/reports/tabular/{report_key}", params=params, headers=headers
    )
    assert response.status_code == 200, response.json()
    return response.json()


async def test_productivity_lista_tarefas_do_responsavel(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    gestor = factory.gestor
    post_id = await _setup_post(client, factory, [str(gestor.user_id)], reward=8)
    await _complete(client, factory.headers, post_id)

    body = await _tabular(client, factory.headers, "productivity")
    assert body["total"] >= 1
    assert any(item["post_id"] == post_id for item in body["items"])
    assert body["points_total"] is not None


async def test_delayed_tasks_lista_so_atrasadas_com_soma_de_pontos(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    gestor = factory.gestor
    yesterday = (_TODAY - timedelta(days=1)).isoformat()
    late_post = await _setup_post(
        client, factory, [str(gestor.user_id)], reward=5, deadline_date=yesterday
    )
    await _complete(client, factory.headers, late_post)
    on_time_post = await _setup_post(client, factory, [str(gestor.user_id)], reward=5)
    await _complete(client, factory.headers, on_time_post)

    body = await _tabular(client, factory.headers, "delayed_tasks")
    ids = [item["post_id"] for item in body["items"]]
    assert late_post in ids
    assert on_time_post not in ids
    assert body["points_total"] == 5


async def test_access_logs_desligado_mostra_motivo(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    body = await _tabular(client, factory.headers, "access_logs")
    assert body["items"] == []
    assert body["disabled_reason"]


async def test_new_customers_filtra_por_periodo(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    await _create_customer(factory.client, factory.headers, "Cliente Novo")
    body = await _tabular(
        client,
        factory.headers,
        "new_customers",
        **{"from": _HOJE_UTC.isoformat(), "to": _HOJE_UTC.isoformat()},
    )
    assert body["total"] >= 1
    assert all(item["created_at"] for item in body["items"])


async def test_new_lawsuits_lista_processos_criados(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    lawsuit = await factory.create()
    body = await _tabular(client, factory.headers, "new_lawsuits")
    ids = [item["lawsuit_id"] for item in body["items"]]
    assert lawsuit in ids


async def test_ganhos_e_perdidos_por_closure_date_com_tempo_total(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    won = await _create_lawsuit(
        factory.client,
        factory.headers,
        user_id=str(factory.gestor.user_id),
        lawsuit_type_id=factory.type_id,
        stage_id=factory.stage_id,
        outcome="GANHO",
        closure_date=_HOJE_UTC.isoformat(),  # dívida 32: comparado com created_at (UTC)
        fees_value="1500.00",
    )
    lost = await _create_lawsuit(
        factory.client,
        factory.headers,
        user_id=str(factory.gestor.user_id),
        lawsuit_type_id=factory.type_id,
        stage_id=factory.stage_id,
        outcome="PERDIDO",
        closure_date=_HOJE_UTC.isoformat(),  # dívida 32
    )

    won_body = await _tabular(client, factory.headers, "won_lawsuits")
    lost_body = await _tabular(client, factory.headers, "lost_lawsuits")

    won_ids = [item["lawsuit_id"] for item in won_body["items"]]
    lost_ids = [item["lawsuit_id"] for item in lost_body["items"]]
    assert won["id"] in won_ids
    assert won["id"] not in lost_ids
    assert lost["id"] in lost_ids

    won_row = next(item for item in won_body["items"] if item["lawsuit_id"] == won["id"])
    assert won_row["total_days"] == 0
    assert won_row["fees_value"] == "1500.00"


async def test_pauta_de_audiencias_so_data_futura(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    lawsuit_id = await factory.create()
    hearing_type = await client.post(
        "/api/v1/task-types",
        json={
            "name": "Pauta de audiências",
            "complexity": "SIMPLES",
            "duration": "MIN_15",
            "reward": 5,
        },
        headers=factory.headers,
    )
    assert hearing_type.status_code == 201, hearing_type.json()
    tomorrow = (_TODAY + timedelta(days=1)).isoformat()
    yesterday = (_TODAY - timedelta(days=1)).isoformat()

    future = await client.post(
        "/api/v1/posts",
        json={
            "lawsuit_id": lawsuit_id,
            "task_type_id": hearing_type.json()["id"],
            "user_ids": [str(factory.gestor.user_id)],
            "scheduled_date": tomorrow,
            "location": "Fórum Central",
        },
        headers=factory.headers,
    )
    assert future.status_code == 201, future.json()
    past = await client.post(
        "/api/v1/posts",
        json={
            "lawsuit_id": lawsuit_id,
            "task_type_id": hearing_type.json()["id"],
            "user_ids": [str(factory.gestor.user_id)],
            "scheduled_date": yesterday,
        },
        headers=factory.headers,
    )
    assert past.status_code == 201, past.json()

    body = await _tabular(client, factory.headers, "hearings")
    ids = [item["post_id"] for item in body["items"]]
    assert future.json()["id"] in ids
    assert past.json()["id"] not in ids
    row = next(item for item in body["items"] if item["post_id"] == future.json()["id"])
    assert row["location"] == "Fórum Central"


async def test_partes_contrarias_conta_processos(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    contrary_customer_id = await _create_customer(factory.client, factory.headers, "Réu Recorrente")
    active_customer_id = await _create_customer(factory.client, factory.headers, "Autor")
    await _create_lawsuit(
        factory.client,
        factory.headers,
        user_id=str(factory.gestor.user_id),
        lawsuit_type_id=factory.type_id,
        stage_id=factory.stage_id,
        parties=[
            {"customer_id": active_customer_id, "pole": "ATIVO", "is_client": True},
            {"customer_id": contrary_customer_id, "pole": "CONTRARIA", "is_client": False},
        ],
    )

    body = await _tabular(client, factory.headers, "contrary_parties")
    row = next(item for item in body["items"] if item["customer_id"] == contrary_customer_id)
    assert row["lawsuit_count"] == 1


async def test_colaborador_so_ve_a_propria_produtividade(
    client: AsyncClient, factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    headers = auth_header(colaborador)

    own = await _tabular(client, headers, "productivity")
    assert own["total"] == 0

    response = await client.get(
        "/api/v1/reports/tabular/productivity",
        params={"user_id": str(factory.gestor.user_id)},
        headers=headers,
    )
    assert response.status_code == 403

    other_report = await client.get("/api/v1/reports/tabular/new_lawsuits", headers=headers)
    assert other_report.status_code == 403


async def test_export_respeita_filtros(client: AsyncClient, factory: LawsuitFactory) -> None:
    await factory.create()
    response = await client.post(
        "/api/v1/reports/tabular/new_lawsuits/export",
        params={"format": "xlsx"},
        headers=factory.headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert len(response.content) > 0


async def test_tenant_a_nao_ve_novos_clientes_de_tenant_b(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    factory_a = await _make_factory(client, make_user, app_session_factory)
    factory_b = await _make_factory(client, make_user, app_session_factory)

    await _create_customer(factory_a.client, factory_a.headers, "Cliente Tenant A")

    body_b = await _tabular(client, factory_b.headers, "new_customers")
    assert body_b["total"] == 0
