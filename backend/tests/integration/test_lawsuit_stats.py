import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import _create_stage
from tests.integration.test_lawsuits_listing import LawsuitFactory, _make_factory
from tests.perf import e_plumbing

_NOW = datetime.now(UTC)
_THIS_MONTH = _NOW.date().replace(day=1)
_LAST_MONTH = (_THIS_MONTH - timedelta(days=1)).replace(day=1)
_TWO_MONTHS_AGO = (_LAST_MONTH - timedelta(days=1)).replace(day=1)

_NEGOCIACAO_STEP_ID = 2


class InMemoryStatsCache:
    """Fake do contrato StatsCache — os testes de cache/budget não tocam o Redis."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, name: str) -> str | None:
        return self.store.get(name)

    async def set(self, name: str, value: str, *, ex: int) -> None:
        self.store[name] = value

    async def delete(self, *names: str) -> None:
        for name in names:
            self.store.pop(name, None)


@pytest.fixture
async def factory(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> LawsuitFactory:
    return await _make_factory(client, make_user, app_session_factory)


async def _create_in_negotiation_step(factory: LawsuitFactory) -> str:
    """Processo numa etapa da fase Negociação (step 2) — a factory padrão usa Marketing."""
    stage_id = await _create_stage(factory.client, factory.headers, step_id=_NEGOCIACAO_STEP_ID)
    return await factory.create(stage_id=stage_id)


async def _seed_dashboard(factory: LawsuitFactory) -> None:
    """Seed determinístico do aceite: 6 ativos (3 já existiam no fim do mês anterior),
    2 fechamentos no mês (2 no anterior — um deles é o processo arquivado), 1
    arquivamento no mês (0 no anterior) e volume 5×Marketing / 1×Negociação."""
    ativo_antigo = await factory.create("Ativo Antigo")
    await factory.backdate_created(ativo_antigo, _NOW.replace(day=1) - timedelta(days=10))
    await factory.create("Ativo Novo")
    await _create_in_negotiation_step(factory)
    await factory.create("Fechado Um", closure_date=str(_THIS_MONTH))
    await factory.create("Fechado Dois", closure_date=str(_THIS_MONTH))
    fechado_anterior = await factory.create("Fechado Anterior", closure_date=str(_LAST_MONTH))
    await factory.backdate_created(fechado_anterior, datetime.combine(_TWO_MONTHS_AGO, _NOW.time()))
    arquivado = await factory.create(
        "Arquivado Mês", closure_date=str(_LAST_MONTH), archived_date=str(_THIS_MONTH)
    )
    await factory.backdate_created(arquivado, datetime.combine(_TWO_MONTHS_AGO, _NOW.time()))


@pytest.mark.commits
async def test_stats_com_seed_deterministico(client: AsyncClient, factory: LawsuitFactory) -> None:
    await _seed_dashboard(factory)
    response = await client.get("/api/v1/lawsuits/stats", headers=factory.headers)
    assert response.status_code == 200
    body = response.json()

    # Regra 3: fechado sem arquivamento continua ativo — 3 "de funil" + 3 fechados.
    assert body["active"] == {"value": 6, "delta_pct": 100.0, "previous": 3}
    # Regra 4: fechamento conta por closure_date, não por created_at — o arquivado do
    # mês também fechou no mês anterior, então a base de comparação é 2.
    assert body["closed_this_month"] == {"value": 2, "delta_pct": 0.0, "previous": 2}
    assert body["archived_this_month"] == {"value": 1, "delta_pct": None, "previous": 0}
    # Regra 5: volume por fase só com ativos, somando 100%.
    assert body["volume_by_step"] == [
        {"step": "Marketing", "count": 5, "pct": 83.3},
        {"step": "Negociação", "count": 1, "pct": 16.7},
    ]
    # Regra 6: meta não configurada → None (o widget convida a configurar).
    assert body["closure_goal"] is None


async def test_stats_mes_parametrizado(client: AsyncClient, factory: LawsuitFactory) -> None:
    await _seed_dashboard(factory)
    response = await client.get(
        "/api/v1/lawsuits/stats",
        params={"month": f"{_LAST_MONTH:%Y-%m}"},
        headers=factory.headers,
    )
    assert response.status_code == 200
    body = response.json()
    # Olhando o mês passado: 2 fechamentos (Fechado Anterior + Arquivado Mês), 0 arquivados.
    assert body["closed_this_month"]["value"] == 2
    assert body["archived_this_month"]["value"] == 0

    invalid = await client.get(
        "/api/v1/lawsuits/stats", params={"month": "2026/01"}, headers=factory.headers
    )
    assert invalid.status_code == 422


async def test_variacao_contra_mes_anterior(client: AsyncClient, factory: LawsuitFactory) -> None:
    # Regra 1: variação compara com o mesmo período do mês anterior — 1 agora, 2 antes.
    await factory.create("Fechado Agora", closure_date=str(_THIS_MONTH))
    await factory.create("Fechado Antes Um", closure_date=str(_LAST_MONTH))
    await factory.create("Fechado Antes Dois", closure_date=str(_LAST_MONTH))

    response = await client.get("/api/v1/lawsuits/stats", headers=factory.headers)
    assert response.json()["closed_this_month"] == {"value": 1, "delta_pct": -50.0, "previous": 2}


async def test_mes_anterior_zerado_vira_novo(client: AsyncClient, factory: LawsuitFactory) -> None:
    # Regra 2: anterior zerado e atual positivo → delta None ("novo"), nunca ∞.
    await factory.create("Arquivado", closure_date=str(_THIS_MONTH), archived_date=str(_THIS_MONTH))
    response = await client.get("/api/v1/lawsuits/stats", headers=factory.headers)
    assert response.json()["archived_this_month"] == {"value": 1, "delta_pct": None, "previous": 0}


async def test_volume_por_fase_soma_cem_por_cento(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    await factory.create("Marketing Um")
    await factory.create("Marketing Dois")
    await _create_in_negotiation_step(factory)
    # Arquivado não entra no volume (regra 5).
    await factory.create("Arquivado", closure_date=str(_THIS_MONTH), archived_date=str(_THIS_MONTH))

    response = await client.get("/api/v1/lawsuits/stats", headers=factory.headers)
    volume = response.json()["volume_by_step"]
    assert sum(item["count"] for item in volume) == 3
    assert sum(item["pct"] for item in volume) == pytest.approx(100.0, abs=0.1)


async def test_cache_invalida_ao_fechar_processo(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    # Regra 7: o cache de 5 minutos não pode segurar o número velho depois do fechamento.
    lawsuit_id = await factory.create("Vai Fechar")
    primeiro = await client.get("/api/v1/lawsuits/stats", headers=factory.headers)
    assert primeiro.json()["closed_this_month"]["value"] == 0

    update = await client.put(
        f"/api/v1/lawsuits/{lawsuit_id}",
        json={
            "user_id": str(factory.gestor.user_id),
            "lawsuit_type_id": factory.type_id,
            "stage_id": factory.stage_id,
            "closure_date": str(_THIS_MONTH),
        },
        headers=factory.headers,
    )
    assert update.status_code == 200

    segundo = await client.get("/api/v1/lawsuits/stats", headers=factory.headers)
    assert segundo.json()["closed_this_month"]["value"] == 1


@pytest.mark.commits
async def test_cache_evita_recomputo(client: AsyncClient, factory: LawsuitFactory) -> None:
    """Segunda leitura no mesmo (tenant, mês) vem do cache — verificável pelo próprio
    contrato: o valor gravado é o JSON completo da resposta."""
    from app.domain.lawsuits.stats import cache_key

    cache = InMemoryStatsCache()
    cache.store[cache_key(factory.gestor.tenant_id, _THIS_MONTH)] = json.dumps(
        {
            "active": {"value": 99, "delta_pct": None, "previous": 0},
            "closed_this_month": {"value": 0, "delta_pct": None, "previous": 0},
            "archived_this_month": {"value": 0, "delta_pct": None, "previous": 0},
            "volume_by_step": [],
            "closure_goal": None,
        }
    )
    async with factory.sessions() as session:
        from sqlalchemy import event

        from app.domain.lawsuits.stats import get_stats

        statements: list[str] = []
        bind = session.get_bind()

        @event.listens_for(bind, "before_cursor_execute", named=True)
        def count_statements(conn: object, cursor: object, statement: str, **kw: object) -> None:
            if not e_plumbing(statement):
                statements.append(statement)

        async with session.begin():
            from app.core.rls import set_tenant_context

            await set_tenant_context(session, factory.gestor.tenant_id)
            stats = await get_stats(session, factory.gestor.tenant_id, _THIS_MONTH, cache)

    assert stats.active.value == 99
    assert statements == []


@pytest.mark.commits
async def test_stats_dentro_do_budget_de_queries(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    for index in range(5):
        await factory.create(f"Budget {index}")

    from sqlalchemy import event

    from app.core.rls import set_tenant_context
    from app.domain.lawsuits.stats import get_stats

    statements: list[str] = []
    async with factory.sessions() as session:
        bind = session.get_bind()

        @event.listens_for(bind, "before_cursor_execute", named=True)
        def count_statements(conn: object, cursor: object, statement: str, **kw: object) -> None:
            if not e_plumbing(statement):
                statements.append(statement)

        async with session.begin():
            await set_tenant_context(session, factory.gestor.tenant_id)
            stats = await get_stats(
                session, factory.gestor.tenant_id, _THIS_MONTH, InMemoryStatsCache()
            )
            assert stats.active.value == 5

    # Budget (spec 028 §8): uma query de agregados condicionais + uma de volume por fase.
    assert len(statements) <= 4
