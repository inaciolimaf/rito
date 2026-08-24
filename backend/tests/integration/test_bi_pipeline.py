"""BI: Estoque e Prospecção (spec 074).

A view materializada bi_pipeline_monthly é estática entre refreshes (regra 8, mesmo
padrão de agility_daily/071): os testes criam processos pela API e chamam
`refresh_bi_pipeline_monthly` direto com a MIGRATIONS_DATABASE_URL — a fila nunca
participa de teste (CLAUDE.md §3). Cada teste trabalha num tenant próprio (factory),
então o refresh global da view não contamina as asserções dos vizinhos: a view barreira
filtra por `app.tenant_id`.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import TypedDict

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.domain.users.models import UserRole
from app.workers.bi_pipeline import refresh_bi_pipeline_monthly
from tests.integration.conftest import SeededUser, auth_header
from tests.integration.test_lawsuits import (
    _create_lawsuit,
    _create_lawsuit_type,
    _create_stage,
)
from tests.integration.test_lawsuits_listing import LawsuitFactory, _make_factory

_NOW = datetime.now(UTC)
_TODAY = _NOW.date()
_THIS_MONTH = _TODAY.replace(day=1)
_LAST_MONTH = (_THIS_MONTH - timedelta(days=1)).replace(day=1)

# Fases fixas do seed da migration 015 (mesma convenção de test_lawsuits.py).
_MARKETING = 1
_NEGOCIACAO = 2
_CONSULTORIA = 3
_JUDICIAL = 5


def _months_back(n: int) -> date:
    """Dia 1 do mês n meses atrás."""
    zero_based = _THIS_MONTH.month - 1 - n
    return date(_THIS_MONTH.year + zero_based // 12, zero_based % 12 + 1, 1)


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
    await refresh_bi_pipeline_monthly(url)


class _ClosedMonthBody(TypedDict):
    value: int
    delta_pct: float | None
    previous: int


class _TrendPointBody(TypedDict):
    month: str
    closed: int


class _PipelineBody(TypedDict):
    opportunities_month: int
    active: int
    archived: int
    idle_120: int
    closed_month: _ClosedMonthBody
    in_service: int
    closed_trend: list[_TrendPointBody]
    staleness_hint: str
    crm_warning: str


class _ConversionGroupBody(TypedDict):
    action_group_id: str
    action_group_name: str
    opportunities: int
    closed: int
    conversion_rate: float | None


class _ConversionBody(TypedDict):
    period: str
    groups: list[_ConversionGroupBody]
    staleness_hint: str


class _PortfolioStepItemBody(TypedDict):
    step_id: int
    step_name: str
    active: int


class _PortfolioStepsBody(TypedDict):
    group_by: str
    items: list[_PortfolioStepItemBody]


class _PortfolioPeriodItemBody(TypedDict):
    month: str
    active: int


class _PortfolioPeriodsBody(TypedDict):
    group_by: str
    items: list[_PortfolioPeriodItemBody]


async def _pipeline(client: AsyncClient, headers: dict[str, str], **params: str) -> _PipelineBody:
    response = await client.get("/api/v1/bi/pipeline", params=params, headers=headers)
    assert response.status_code == 200, response.json()
    return response.json()  # type: ignore[no-any-return]


async def _conversion(
    client: AsyncClient, headers: dict[str, str], **params: str
) -> _ConversionBody:
    response = await client.get("/api/v1/bi/pipeline/conversion", params=params, headers=headers)
    assert response.status_code == 200, response.json()
    return response.json()  # type: ignore[no-any-return]


async def _portfolio_steps(
    client: AsyncClient, headers: dict[str, str], **params: str
) -> _PortfolioStepsBody:
    response = await client.get(
        "/api/v1/bi/pipeline/portfolio",
        params={"group_by": "step", **params},
        headers=headers,
    )
    assert response.status_code == 200, response.json()
    return response.json()  # type: ignore[no-any-return]


async def _portfolio_periods(
    client: AsyncClient, headers: dict[str, str], **params: str
) -> _PortfolioPeriodsBody:
    response = await client.get(
        "/api/v1/bi/pipeline/portfolio",
        params={"group_by": "period", **params},
        headers=headers,
    )
    assert response.status_code == 200, response.json()
    return response.json()  # type: ignore[no-any-return]


async def _stage_in_step(client: AsyncClient, headers: dict[str, str], step_id: int) -> str:
    return await _create_stage(client, headers, step_id)


async def test_seis_indicadores_com_seed_deterministico(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regras 1–6: os 6 indicadores conferem com um cenário controlado."""
    judicial = await _stage_in_step(client, factory.headers, _JUDICIAL)
    marketing = await _stage_in_step(client, factory.headers, _MARKETING)
    negociacao = await _stage_in_step(client, factory.headers, _NEGOCIACAO)

    # Ativo com movimento recente (não parado).
    moved_today = await factory.create("Ativo Movido", stage_id=judicial)
    await factory.move(moved_today, 0)
    # Ativo parado há 130 dias.
    idle = await factory.create("Ativo Parado", stage_id=judicial)
    await factory.move(idle, 130)
    # Prospecção: Marketing e Negociação → em atendimento, fora dos "ativos" (regra 2/6).
    await factory.create("Em Marketing", stage_id=marketing)
    await factory.create("Em Negociacao", stage_id=negociacao)
    # Fechado neste mês, ainda não arquivado → ativo + fechamento.
    await factory.create("Fechado Mês", stage_id=judicial, closure_date=str(_TODAY))
    # Arquivado neste mês → fora dos ativos (regra 3).
    await factory.create(
        "Arquivado",
        stage_id=judicial,
        closure_date=str(_TODAY),
        archived_date=str(_TODAY),
    )
    await _refresh()

    result = await _pipeline(client, factory.headers)
    # Regra 1: os 6 processos entraram no mês (coorte da view).
    assert result["opportunities_month"] == 6
    # Regra 2: movido + parado + fechado-não-arquivado (arquivado e prospecção fora).
    assert result["active"] == 3
    # Regra 3: archived_date preenchida.
    assert result["archived"] == 1
    # Regra 4: parado 130d + o fechado sem nenhuma movimentação (nulo conta como parado).
    assert result["idle_120"] == 2
    # Regra 6: Marketing + Negociação.
    assert result["in_service"] == 2
    # Regra 5: dois fechamentos no mês, mês anterior zerado → variação "novo" (None).
    closed_month = result["closed_month"]
    assert isinstance(closed_month, dict)
    assert closed_month["value"] == 2
    assert closed_month["previous"] == 0
    assert closed_month["delta_pct"] is None
    # Regras 8 e 12: a aba sempre carrega os dois avisos.
    assert "480 min" in str(result["staleness_hint"])
    assert "CRM" in str(result["crm_warning"])


async def test_parados_120_inclui_last_movement_nulo(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 4: `last_movement_at` nulo (nunca movimentado) conta como parado."""
    judicial = await _stage_in_step(client, factory.headers, _JUDICIAL)
    recent = await factory.create("Movido Recentemente", stage_id=judicial)
    await factory.move(recent, 10)
    old = await factory.create("Movido Ha Muito", stage_id=judicial)
    await factory.move(old, 121)
    await factory.create("Nunca Movido", stage_id=judicial)

    result = await _pipeline(client, factory.headers)
    assert result["active"] == 3
    assert result["idle_120"] == 2


async def test_fechamentos_com_variacao_e_serie_de_seis_meses(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 5: variação vs mês anterior e série de 6 meses com meses zerados."""
    judicial = await _stage_in_step(client, factory.headers, _JUDICIAL)
    await factory.create("Fechado 1", stage_id=judicial, closure_date=str(_TODAY))
    await factory.create("Fechado 2", stage_id=judicial, closure_date=str(_THIS_MONTH))
    await factory.create(
        "Fechado Mês Passado", stage_id=judicial, closure_date=str(_LAST_MONTH + timedelta(days=14))
    )
    three_months_ago = _months_back(3)
    await factory.create(
        "Fechado 3 Meses",
        stage_id=judicial,
        closure_date=str(three_months_ago + timedelta(days=14)),
    )

    result = await _pipeline(client, factory.headers)
    closed_month = result["closed_month"]
    assert isinstance(closed_month, dict)
    assert closed_month["value"] == 2
    assert closed_month["previous"] == 1
    assert closed_month["delta_pct"] == pytest.approx(100.0)

    trend = result["closed_trend"]
    assert isinstance(trend, list)
    assert [point["month"] for point in trend] == [
        _months_back(offset).isoformat() for offset in range(5, -1, -1)
    ]
    by_month = {point["month"]: point["closed"] for point in trend}
    assert by_month[_THIS_MONTH.isoformat()] == 2
    assert by_month[_LAST_MONTH.isoformat()] == 1
    assert by_month[three_months_ago.isoformat()] == 1
    # Meses sem fechamento aparecem zerados, não somem.
    assert by_month[_months_back(2).isoformat()] == 0
    assert by_month[_months_back(4).isoformat()] == 0
    assert by_month[_months_back(5).isoformat()] == 0


async def test_conversao_por_grupo(client: AsyncClient, factory: LawsuitFactory) -> None:
    """Regra 7: taxa = fechados ÷ oportunidades da coorte, por grupo de ação."""
    factory_group_id = await _factory_group_id(client, factory)
    # Grupo da factory: 2 oportunidades, 1 fechado → 50%.
    await factory.create("Oportunidade A", closure_date=str(_TODAY))
    await factory.create("Oportunidade B")
    # Segundo grupo: 4 oportunidades, 1 fechado → 25%.
    other_type_id, other_group_id = await _create_lawsuit_type(client, factory.headers)
    stage_id = await _create_stage(client, factory.headers, _NEGOCIACAO)
    for index in range(4):
        extra = {"closure_date": str(_TODAY)} if index == 0 else {}
        await _create_lawsuit(
            client,
            factory.headers,
            user_id=str(factory.gestor.user_id),
            lawsuit_type_id=other_type_id,
            stage_id=stage_id,
            **extra,
        )
    await _refresh()

    result = await _conversion(client, factory.headers, period=f"{_THIS_MONTH:%Y-%m}")
    groups = {str(group["action_group_id"]): group for group in result["groups"]}
    factory_group = groups[factory_group_id]
    assert factory_group["opportunities"] == 2
    assert factory_group["closed"] == 1
    assert factory_group["conversion_rate"] == pytest.approx(50.0)
    other_group = groups[other_group_id]
    assert other_group["opportunities"] == 4
    assert other_group["closed"] == 1
    assert other_group["conversion_rate"] == pytest.approx(25.0)


async def _factory_group_id(client: AsyncClient, factory: LawsuitFactory) -> str:
    """O grupo do tipo de ação criado pela factory (ela não expõe o id)."""
    response = await client.get("/api/v1/action-groups", headers=factory.headers)
    assert response.status_code == 200
    groups = response.json()["items"]
    # A factory cria exatamente um grupo no tenant deste teste.
    assert len(groups) == 1
    return str(groups[0]["id"])


async def test_conversao_com_zero_oportunidades_nunca_zero_porcento(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 11: divisão por zero → null (a UI exibe "—"), nunca 0% ou NaN."""
    await _create_lawsuit_type(client, factory.headers)  # grupo sem nenhum processo
    await _refresh()

    result = await _conversion(client, factory.headers, period=f"{_THIS_MONTH:%Y-%m}")
    rates = [group["conversion_rate"] for group in result["groups"]]
    assert all(rate is None for rate in rates)


async def test_grupo_sem_movimento_aparece_zerado(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 10: grupo sem processos no período aparece na lista, zerado — não some."""
    await factory.create("Único Processo")
    _empty_type_id, empty_group_id = await _create_lawsuit_type(client, factory.headers)
    await _refresh()

    result = await _conversion(client, factory.headers, period=f"{_THIS_MONTH:%Y-%m}")
    groups = {str(group["action_group_id"]): group for group in result["groups"]}
    assert empty_group_id in groups
    empty = groups[empty_group_id]
    assert empty["opportunities"] == 0
    assert empty["closed"] == 0
    assert empty["conversion_rate"] is None


async def test_grafico_vem_da_view_e_relatorio_e_tempo_real(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 8: funil/conversão (gráficos) só mudam após o refresh; o resumo da
    carteira (rodapé) reflete o banco na hora."""
    judicial = await _stage_in_step(client, factory.headers, _JUDICIAL)
    await factory.create("Processo Novo", stage_id=judicial)

    # Antes do refresh: a conversão (view) não conhece o processo…
    before = await _conversion(client, factory.headers, period=f"{_THIS_MONTH:%Y-%m}")
    assert all(group["opportunities"] == 0 for group in before["groups"])
    # …mas o relatório de carteira (tempo real) já conta.
    portfolio = await _portfolio_steps(client, factory.headers)
    steps = {item["step_name"]: item["active"] for item in portfolio["items"]}
    assert steps["Judicial"] == 1

    await _refresh()

    after = await _conversion(client, factory.headers, period=f"{_THIS_MONTH:%Y-%m}")
    total_opportunities = sum(group["opportunities"] for group in after["groups"])
    assert total_opportunities == 1


async def test_refresh_da_view_atualiza_os_numeros(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 8: o indicador de oportunidades (view) só reflete o cadastro após refresh."""
    before = await _pipeline(client, factory.headers)
    assert before["opportunities_month"] == 0

    await factory.create("Nova Oportunidade")
    stale = await _pipeline(client, factory.headers)
    assert stale["opportunities_month"] == 0

    await _refresh()
    fresh = await _pipeline(client, factory.headers)
    assert fresh["opportunities_month"] == 1


async def test_colaborador_recebe_403(
    client: AsyncClient,
    factory: LawsuitFactory,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Regra 9: a aba exige ADMINISTRADOR ou GESTOR — Colaborador é barrado nos 3 endpoints."""
    colaborador = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    headers = auth_header(colaborador)

    for path in (
        "/api/v1/bi/pipeline",
        "/api/v1/bi/pipeline/conversion",
        "/api/v1/bi/pipeline/portfolio",
    ):
        response = await client.get(path, headers=headers)
        assert response.status_code == 403, path


async def test_tenant_a_nao_ve_funil_de_tenant_b(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """CLAUDE.md §4: a view barreira embute o filtro de tenant — tenant B não enxerga
    a coorte de A nem com a view refrescada."""
    factory_a = await _make_factory(client, make_user, app_session_factory)
    factory_b = await _make_factory(client, make_user, app_session_factory)

    await factory_a.create("Processo de A", closure_date=str(_TODAY))
    await _refresh()

    pipeline_b = await _pipeline(client, factory_b.headers)
    assert pipeline_b["opportunities_month"] == 0

    conversion_b = await _conversion(client, factory_b.headers, period=f"{_THIS_MONTH:%Y-%m}")
    assert all(group["opportunities"] == 0 for group in conversion_b["groups"])


async def test_portfolio_por_periodo_agrupa_mes_de_criacao(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Resumo da carteira por período (tempo real): ativos por mês de criação."""
    await factory.create("Deste Mês")
    last_month = await factory.create("Do Mês Passado")
    await factory.backdate_created(
        last_month, datetime.combine(_LAST_MONTH, datetime.min.time(), tzinfo=UTC)
    )
    # Arquivado não entra na carteira.
    await factory.create("Arquivado", closure_date=str(_TODAY), archived_date=str(_TODAY))

    result = await _portfolio_periods(client, factory.headers)
    assert result["group_by"] == "period"
    by_month = {item["month"]: item["active"] for item in result["items"]}
    assert by_month[_THIS_MONTH.isoformat()] == 1
    assert by_month[_LAST_MONTH.isoformat()] == 1
