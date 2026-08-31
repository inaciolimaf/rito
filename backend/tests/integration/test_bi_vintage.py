"""BI: Safra e Qualidade (spec 075).

A tabela de safra vem da view materializada bi_vintage (estática entre refreshes, mesmo
padrão da 074): os testes criam processos pela API e chamam `refresh_bi_vintage` direto
com a MIGRATIONS_DATABASE_URL — a fila nunca participa de teste (CLAUDE.md §3). A taxa
de sucesso por período e a série mensal são tempo real (a view é anual, §9.2 da 074) e
dispensam refresh. Cada teste trabalha num tenant próprio (factory), então o refresh
global não contamina vizinhos: a view barreira filtra por `app.tenant_id`.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TypedDict

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.domain.users.models import UserRole
from app.workers.bi_vintage import refresh_bi_vintage
from tests.integration.conftest import SeededUser, auth_header
from tests.integration.test_bi_pipeline import _factory_group_id
from tests.integration.test_lawsuits import (
    _create_lawsuit,
    _create_lawsuit_type,
    _create_stage,
)
from tests.integration.test_lawsuits_listing import LawsuitFactory, _make_factory

_NOW = datetime.now(UTC)
_TODAY = _NOW.date()
_THIS_MONTH = _TODAY.replace(day=1)

# Fases fixas do seed da migration 015 (mesma convenção de test_lawsuits.py).
_JUDICIAL = 5


@pytest.fixture
async def factory(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> LawsuitFactory:
    return await _make_factory(client, make_user, app_session_factory)


async def _refresh() -> None:
    url = get_settings().migrations_database_url
    assert url is not None
    await refresh_bi_vintage(url)


class _VintageYearBody(TypedDict):
    vintage_year: int
    total: int
    won: int
    lost: int
    settled: int
    in_progress: int
    transited: int
    archived: int
    avg_cycle_days: float | None
    success_rate: float | None
    small_sample: bool
    rate_change_pp: float | None
    highlighted: bool


class _VintageBody(TypedDict):
    years: list[_VintageYearBody]
    staleness_hint: str


class _SuccessGroupBody(TypedDict):
    action_group_id: str
    action_group_name: str
    won: int
    lost: int
    settled: int
    concluded: int
    success_rate: float | None
    small_sample: bool


class _SuccessRateBody(TypedDict):
    period: str
    groups: list[_SuccessGroupBody]
    rate_note: str


class _TrendPointBody(TypedDict):
    month: str
    won: int
    lost: int
    settled: int
    concluded: int
    success_rate: float | None


class _TrendBody(TypedDict):
    months: int
    points: list[_TrendPointBody]
    rate_note: str


async def _vintage(client: AsyncClient, headers: dict[str, str], **params: str) -> _VintageBody:
    response = await client.get("/api/v1/bi/vintage", params=params, headers=headers)
    assert response.status_code == 200, response.json()
    return response.json()  # type: ignore[no-any-return]


async def _success_rate(
    client: AsyncClient, headers: dict[str, str], **params: str
) -> _SuccessRateBody:
    response = await client.get("/api/v1/bi/success-rate", params=params, headers=headers)
    assert response.status_code == 200, response.json()
    return response.json()  # type: ignore[no-any-return]


async def _trend(client: AsyncClient, headers: dict[str, str], **params: str) -> _TrendBody:
    response = await client.get("/api/v1/bi/success-rate/trend", params=params, headers=headers)
    assert response.status_code == 200, response.json()
    return response.json()  # type: ignore[no-any-return]


def _year_of(vintage: _VintageBody, year: int) -> _VintageYearBody:
    matches = [row for row in vintage["years"] if row["vintage_year"] == year]
    assert len(matches) == 1, f"safra {year} ausente ou duplicada: {vintage['years']}"
    return matches[0]


async def test_taxa_ignora_processos_em_tramitacao(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 1: só concluídos (`outcome` preenchido) entram na taxa — fechado sem
    resultado e processo ainda sem fechamento ficam de fora."""
    await factory.create("Ganho", closure_date=str(_TODAY), outcome="GANHO")
    await factory.create("Fechado Sem Resultado", closure_date=str(_TODAY))
    await factory.create("Em Tramitacao")

    result = await _success_rate(client, factory.headers, period=f"{_THIS_MONTH:%Y-%m}")
    group = result["groups"][0]
    assert group["won"] == 1
    assert group["concluded"] == 1
    assert group["success_rate"] == pytest.approx(100.0)
    # Regra 2: o critério da taxa viaja na resposta para o tooltip da UI.
    assert "Acordos entram no denominador" in result["rate_note"]


async def test_acordo_no_denominador_fora_do_numerador(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 2: taxa = ganhos ÷ (ganhos + perdidos + acordos) — 1/3, não 1/2."""
    await factory.create("Ganho", closure_date=str(_TODAY), outcome="GANHO")
    await factory.create("Perdido", closure_date=str(_TODAY), outcome="PERDIDO")
    await factory.create("Acordo", closure_date=str(_TODAY), outcome="ACORDO")

    result = await _success_rate(client, factory.headers, period=f"{_THIS_MONTH:%Y-%m}")
    group = result["groups"][0]
    assert group["won"] == 1
    assert group["lost"] == 1
    assert group["settled"] == 1
    assert group["concluded"] == 3
    assert group["success_rate"] == pytest.approx(33.3)


@pytest.mark.commits
async def test_safra_agrupa_por_ano_de_closure_date(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 3: safra = ano de `closure_date`, não de criação — os 3 processos foram
    criados agora, mas caem em safras distintas pelo fechamento."""
    await factory.create("Fechado 2023", closure_date="2023-05-10", outcome="GANHO")
    await factory.create("Fechado 2024", closure_date="2024-05-10", outcome="GANHO")
    await factory.create("Fechado 2024 B", closure_date="2024-11-20", outcome="PERDIDO")
    # Sem fechamento: não entra em safra nenhuma.
    await factory.create("Sem Fechamento")
    await _refresh()

    result = await _vintage(client, factory.headers)
    assert [row["vintage_year"] for row in result["years"]] == [2023, 2024]
    assert _year_of(result, 2023)["total"] == 1
    assert _year_of(result, 2024)["total"] == 2
    assert "480 min" in result["staleness_hint"]


@pytest.mark.commits
async def test_tabela_de_safra_com_os_oito_campos(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 4: total, ganhos, perdidos, acordos, em andamento, transitados,
    arquivados e ciclo médio — todos por ano de fechamento."""
    await factory.create("Ganho", closure_date="2024-03-01", outcome="GANHO")
    await factory.create("Perdido", closure_date="2024-03-01", outcome="PERDIDO")
    await factory.create("Acordo", closure_date="2024-03-01", outcome="ACORDO")
    await factory.create("Em Andamento", closure_date="2024-03-01")
    await factory.create(
        "Arquivado",
        closure_date="2024-03-01",
        outcome="GANHO",
        transit_date="2024-06-01",
        archived_date="2024-06-21",
    )
    await _refresh()

    row = _year_of(await _vintage(client, factory.headers), 2024)
    assert row["total"] == 5
    assert row["won"] == 2
    assert row["lost"] == 1
    assert row["settled"] == 1
    assert row["in_progress"] == 1
    assert row["transited"] == 1
    assert row["archived"] == 1
    # 2024-03-01 → 2024-06-21 = 112 dias; ciclo médio só do arquivado (regra 7).
    assert row["avg_cycle_days"] == pytest.approx(112.0)


async def test_menos_de_10_concluidos_aviso_de_amostra(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 5: grupo com menos de 10 concluídos no período exibe aviso de amostra;
    com 10 ou mais, não."""
    # O grupo da factory é identificado ANTES de criar o segundo — _factory_group_id
    # assume exatamente um grupo no tenant.
    factory_group_id = await _factory_group_id(client, factory)
    await factory.create("Ganho", closure_date=str(_TODAY), outcome="GANHO")
    await factory.create("Perdido", closure_date=str(_TODAY), outcome="PERDIDO")
    # Segundo grupo com 10 concluídos — sem aviso.
    other_type_id, other_group_id = await _create_lawsuit_type(client, factory.headers)
    stage_id = await _create_stage(client, factory.headers, _JUDICIAL)
    for _ in range(10):
        await _create_lawsuit(
            client,
            factory.headers,
            user_id=str(factory.gestor.user_id),
            lawsuit_type_id=other_type_id,
            stage_id=stage_id,
            closure_date=str(_TODAY),
            outcome="GANHO",
        )

    result = await _success_rate(client, factory.headers, period=f"{_THIS_MONTH:%Y-%m}")
    groups = {str(group["action_group_id"]): group for group in result["groups"]}
    small = groups[factory_group_id]
    assert small["concluded"] == 2
    assert small["small_sample"] is True
    big = groups[other_group_id]
    assert big["concluded"] == 10
    assert big["small_sample"] is False


@pytest.mark.commits
async def test_ciclo_medio_so_entre_arquivados(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 7: `archived_date` − `closure_date`, só entre arquivados — o concluído
    não arquivado não entra na média (seriam 100 dias se entrasse)."""
    await factory.create("Ganho Nao Arquivado", closure_date="2024-01-01", outcome="GANHO")
    await factory.create(
        "Arquivado",
        closure_date="2024-01-01",
        outcome="PERDIDO",
        transit_date="2024-01-31",
        archived_date="2024-02-10",  # 40 dias de ciclo
    )
    await _refresh()

    row = _year_of(await _vintage(client, factory.headers), 2024)
    assert row["archived"] == 1
    assert row["avg_cycle_days"] == pytest.approx(40.0)


@pytest.mark.commits
async def test_safra_sem_fechamento_nao_aparece(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 8: ano sem nenhum fechamento não tem linha na tabela — mesmo dentro da
    janela pedida."""
    await factory.create("Fechado 2024", closure_date="2024-05-10", outcome="GANHO")
    await factory.create("Sem Fechamento")
    await _refresh()

    result = await _vintage(client, factory.headers, from_year="2020", to_year="2026")
    assert [row["vintage_year"] for row in result["years"]] == [2024]


@pytest.mark.commits
async def test_variacao_acima_de_10pp_entre_safras_e_destacada(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 9: 50% (2023) → 80% (2024) é +30 p.p., destacado; 80% → 80% (2025), não.
    A primeira safra nunca tem comparação."""
    await factory.create("2023 Ganho", closure_date="2023-05-10", outcome="GANHO")
    await factory.create("2023 Perdido", closure_date="2023-05-10", outcome="PERDIDO")
    for index in range(4):
        await factory.create(f"2024 Ganho {index}", closure_date="2024-05-10", outcome="GANHO")
    await factory.create("2024 Perdido", closure_date="2024-05-10", outcome="PERDIDO")
    for index in range(4):
        await factory.create(f"2025 Ganho {index}", closure_date="2025-05-10", outcome="GANHO")
    await factory.create("2025 Perdido", closure_date="2025-05-10", outcome="PERDIDO")
    await _refresh()

    result = await _vintage(client, factory.headers)
    year_2023 = _year_of(result, 2023)
    assert year_2023["success_rate"] == pytest.approx(50.0)
    assert year_2023["rate_change_pp"] is None
    assert year_2023["highlighted"] is False
    year_2024 = _year_of(result, 2024)
    assert year_2024["success_rate"] == pytest.approx(80.0)
    assert year_2024["rate_change_pp"] == pytest.approx(30.0)
    assert year_2024["highlighted"] is True
    year_2025 = _year_of(result, 2025)
    assert year_2025["rate_change_pp"] == pytest.approx(0.0)
    assert year_2025["highlighted"] is False


@pytest.mark.commits
async def test_zero_concluidos_taxa_traco(client: AsyncClient, factory: LawsuitFactory) -> None:
    """Regra 11: divisão por zero → null (a UI exibe "—"), nunca 0% ou NaN — na safra
    sem nenhum concluído e no período sem concluídos."""
    await factory.create("Fechado Sem Resultado", closure_date="2024-05-10")
    await _refresh()

    row = _year_of(await _vintage(client, factory.headers), 2024)
    assert row["total"] == 1
    assert row["in_progress"] == 1
    assert row["success_rate"] is None

    result = await _success_rate(client, factory.headers, period=f"{_THIS_MONTH:%Y-%m}")
    assert all(group["concluded"] == 0 for group in result["groups"])
    assert all(group["success_rate"] is None for group in result["groups"])


async def test_colaborador_recebe_403(
    client: AsyncClient,
    factory: LawsuitFactory,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Regra 10: a aba exige ADMINISTRADOR ou GESTOR — Colaborador é barrado nos 3 endpoints."""
    colaborador = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    headers = auth_header(colaborador)

    for path in (
        "/api/v1/bi/vintage",
        "/api/v1/bi/success-rate",
        "/api/v1/bi/success-rate/trend",
    ):
        response = await client.get(path, headers=headers)
        assert response.status_code == 403, path


async def test_trend_cobre_24_meses_com_taxa_por_mes(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 6: a série tem os últimos 24 meses terminando no mês corrente; mês sem
    concluído aparece zerado com taxa null, nunca some."""
    await factory.create("Ganho Deste Mês", closure_date=str(_TODAY), outcome="GANHO")

    result = await _trend(client, factory.headers)
    assert result["months"] == 24
    points = result["points"]
    assert len(points) == 24
    assert points[-1]["month"] == _THIS_MONTH.isoformat()
    assert points[-1]["concluded"] == 1
    assert points[-1]["success_rate"] == pytest.approx(100.0)
    assert all(point["concluded"] == 0 for point in points[:-1])
    assert all(point["success_rate"] is None for point in points[:-1])
    # Mesma nota de critério do endpoint de taxa (regra 2).
    assert "Acordos entram no denominador" in result["rate_note"]


async def test_tenant_a_nao_ve_safra_de_tenant_b(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """CLAUDE.md §4: a view barreira embute o filtro de tenant — tenant B não enxerga
    a safra de A nem com a view refrescada (matview não tem RLS)."""
    factory_a = await _make_factory(client, make_user, app_session_factory)
    factory_b = await _make_factory(client, make_user, app_session_factory)

    await factory_a.create("Ganho de A", closure_date="2024-05-10", outcome="GANHO")
    await _refresh()

    vintage_b = await _vintage(client, factory_b.headers)
    assert vintage_b["years"] == []

    success_b = await _success_rate(client, factory_b.headers, period=f"{_THIS_MONTH:%Y-%m}")
    assert all(group["concluded"] == 0 for group in success_b["groups"])
