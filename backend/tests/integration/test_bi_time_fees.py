"""BI: Tempo e Honorários (spec 076).

Tudo vem da view materializada bi_lawsuit_cycles (estática entre refreshes, mesmo
padrão das 074/075): os testes criam processos e lançamentos pela API e chamam
`refresh_bi_cycles` direto com a MIGRATIONS_DATABASE_URL — a fila nunca participa de
teste (CLAUDE.md §3). Cada teste trabalha num tenant próprio (factory), então o
refresh global não contamina vizinhos: a view barreira filtra por `app.tenant_id`.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import TypedDict

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.domain.users.models import FinancialAccess, UserRole
from app.workers.bi_cycles import refresh_bi_cycles
from tests.clock import hoje
from tests.integration.conftest import SeededUser, auth_header
from tests.integration.test_bi_pipeline import _factory_group_id
from tests.integration.test_lawsuits import (
    _create_customer,
    _create_lawsuit,
    _create_lawsuit_type,
)
from tests.integration.test_lawsuits_listing import LawsuitFactory, _make_factory
from tests.integration.test_transactions import (
    _create_account,
    _create_category,
    _create_cost_center,
)

_NOW = datetime.now(UTC)
# Spec 114: o dia é o do ESCRITÓRIO. `_NOW` continua UTC porque é carimbo de tempo,
# mas `_NOW.date()` era o dia UTC — três horas à frente de São Paulo, que é o fuso em
# que as fixtures criam a conta. O `DTZ` não pega este caso: `datetime.now(UTC)` TEM
# fuso, só que o fuso errado para a pergunta «que dia é hoje no escritório».
_TODAY = hoje()


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
    await refresh_bi_cycles(url)


class _CyclesBody(TypedDict):
    prospecting_days: float | None
    production_days: float | None
    execution_days: float | None
    full_cycle_days: float | None


class _TimeFeesBody(TypedDict):
    lawsuits: int
    avg_fees: float | None
    avg_monthly_fees: float | None
    cycles: _CyclesBody
    staleness_hint: str


class _GroupItemBody(TypedDict):
    action_group_id: str
    action_group_name: str
    lawsuits: int
    cycles: _CyclesBody


class _ByGroupBody(TypedDict):
    groups: list[_GroupItemBody]
    staleness_hint: str


class _TypeItemBody(TypedDict):
    lawsuit_type_id: str
    lawsuit_type_name: str
    lawsuits: int
    monthly_profitability: float | None
    small_sample: bool


class _ByTypeBody(TypedDict):
    types: list[_TypeItemBody]
    staleness_hint: str


class _LostTimeBody(TypedDict):
    zero_revenue_lawsuits: int
    lost_months: float
    staleness_hint: str


async def _time_fees(client: AsyncClient, headers: dict[str, str], **params: str) -> _TimeFeesBody:
    # `from` é palavra reservada — os testes passam `from_` e aqui vira o alias da API.
    query = {("from" if key == "from_" else key): value for key, value in params.items()}
    response = await client.get("/api/v1/bi/time-fees", params=query, headers=headers)
    assert response.status_code == 200, response.json()
    return response.json()  # type: ignore[no-any-return]


async def _by_group(client: AsyncClient, headers: dict[str, str]) -> _ByGroupBody:
    response = await client.get("/api/v1/bi/time-fees/by-group", headers=headers)
    assert response.status_code == 200, response.json()
    return response.json()  # type: ignore[no-any-return]


async def _by_type(client: AsyncClient, headers: dict[str, str], **params: str) -> _ByTypeBody:
    response = await client.get("/api/v1/bi/time-fees/by-type", params=params, headers=headers)
    assert response.status_code == 200, response.json()
    return response.json()  # type: ignore[no-any-return]


async def _lost_time(client: AsyncClient, headers: dict[str, str]) -> _LostTimeBody:
    response = await client.get("/api/v1/bi/time-fees/lost-time", headers=headers)
    assert response.status_code == 200, response.json()
    return response.json()  # type: ignore[no-any-return]


async def _create_closed(
    factory: LawsuitFactory,
    *,
    fees: str,
    closure: date,
    transit: date | None = None,
    archived: date | None = None,
    outcome: str | None = None,
    created: datetime | None = None,
    lawsuit_type_id: str | None = None,
) -> tuple[str, str]:
    """Processo fechado com datas controladas — devolve (lawsuit_id, customer_id)
    porque lançamento vinculado ao processo exige o cliente (spec 056, CHECK)."""
    customer_id = await _create_customer(
        factory.client, factory.headers, f"Cliente {uuid.uuid4().hex[:8]}"
    )
    extra: dict[str, object] = {"closure_date": str(closure), "fees_value": fees}
    if transit is not None:
        extra["transit_date"] = str(transit)
    if archived is not None:
        extra["archived_date"] = str(archived)
    if outcome is not None:
        extra["outcome"] = outcome
    lawsuit = await _create_lawsuit(
        factory.client,
        factory.headers,
        user_id=str(factory.gestor.user_id),
        lawsuit_type_id=lawsuit_type_id or factory.type_id,
        stage_id=factory.stage_id,
        parties=[{"customer_id": customer_id, "pole": "ATIVO", "is_client": True}],
        **extra,
    )
    lawsuit_id = str(lawsuit["id"])
    if created is not None:
        await factory.backdate_created(lawsuit_id, created)
    return lawsuit_id, customer_id


async def _financial_fixtures(client: AsyncClient, headers: dict[str, str]) -> tuple[str, str, str]:
    """(receita_category_id, cost_center_id, account_id) — mesmo setup da spec 056."""
    category_id = await _create_category(client, headers, type_="RECEITA", dre_group_id=1)
    cost_center_id = await _create_cost_center(client, headers)
    account_id = await _create_account(client, headers)
    return category_id, cost_center_id, account_id


async def _add_revenue(
    client: AsyncClient,
    headers: dict[str, str],
    fixtures: tuple[str, str, str],
    *,
    lawsuit_id: str,
    customer_id: str,
    amount: str,
    paid: bool = True,
    internal: bool = False,
) -> None:
    """Receita vinculada ao processo; `paid` controla `payment_date`, `internal`
    marca lançamento de controle (spec 058) — os dois eixos da regra 6."""
    category_id, cost_center_id, account_id = fixtures
    payload: dict[str, object] = {
        "kind": "RECEITA",
        "debit_account_id": account_id,
        "category_id": category_id,
        "cost_center_id": cost_center_id,
        "customer_id": customer_id,
        "lawsuit_id": lawsuit_id,
        "amount": amount,
        "due_date": str(_TODAY),
        "is_internal": internal,
    }
    if paid:
        payload["payment_date"] = str(_TODAY)
    response = await client.post("/api/v1/transactions", json=payload, headers=headers)
    assert response.status_code == 201, response.text


@pytest.mark.commits
async def test_media_de_honorarios_por_processo(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 3: média = soma de `fees_value` ÷ processos no filtro — quem não declarou
    honorários entra no denominador (conta como zero)."""
    await _create_closed(factory, fees="1000.00", closure=date(2024, 3, 1))
    await _create_closed(factory, fees="3000.00", closure=date(2024, 3, 1))
    await _create_closed(factory, fees="0.00", closure=date(2024, 3, 1))
    await _refresh()

    result = await _time_fees(client, factory.headers)
    assert result["lawsuits"] == 3
    assert result["avg_fees"] == pytest.approx(1333.33)
    assert "480 min" in result["staleness_hint"]


@pytest.mark.commits
async def test_media_mensal_penaliza_processo_longo_e_barato(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 4: média mensal = média de (honorários ÷ meses de duração) — o processo
    longo e barato derruba o indicador, exatamente o que ele quer mostrar."""
    # Curto e caro: 60 dias de rotação (2 meses), 6000 de honorários → 3000/mês.
    await _create_closed(
        factory,
        fees="6000.00",
        created=datetime(2024, 3, 1, tzinfo=UTC),
        closure=date(2024, 3, 11),
        transit=date(2024, 4, 1),
        archived=date(2024, 4, 30),
    )
    # Longo e barato: 335 dias de rotação, 100 de honorários → ~9/mês.
    await _create_closed(
        factory,
        fees="100.00",
        created=datetime(2024, 1, 1, tzinfo=UTC),
        closure=date(2024, 2, 1),
        transit=date(2024, 7, 1),
        archived=date(2024, 12, 1),
    )
    await _refresh()

    result = await _time_fees(client, factory.headers)
    assert result["lawsuits"] == 2
    assert result["avg_fees"] == pytest.approx(3050.00)
    expected_monthly = (6000 / (60 / 30) + 100 / (335 / 30)) / 2
    assert result["avg_monthly_fees"] == pytest.approx(expected_monthly, abs=0.01)
    # As 4 médias de ciclo também vêm da view (regras 1 e 2).
    assert result["cycles"]["prospecting_days"] == pytest.approx(20.5)
    assert result["cycles"]["full_cycle_days"] == pytest.approx(197.5)


@pytest.mark.commits
async def test_tempo_perdido_soma_so_os_sem_receita(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 5: tempo perdido = meses dos processos com `revenue = 0` e rotação
    completa maior que zero — quem recebeu e quem não terminou o ciclo ficam fora."""
    fixtures = await _financial_fixtures(client, factory.headers)
    # Com receita paga: 60 dias de ciclo, NÃO conta.
    with_revenue_id, with_revenue_customer = await _create_closed(
        factory,
        fees="500.00",
        created=datetime(2024, 3, 1, tzinfo=UTC),
        closure=date(2024, 3, 11),
        archived=date(2024, 4, 30),
    )
    await _add_revenue(
        client,
        factory.headers,
        fixtures,
        lawsuit_id=with_revenue_id,
        customer_id=with_revenue_customer,
        amount="500.00",
    )
    # Sem receita: 60 dias (2 meses) + 90 dias (3 meses) = 5 meses perdidos.
    await _create_closed(
        factory,
        fees="0.00",
        created=datetime(2024, 3, 1, tzinfo=UTC),
        closure=date(2024, 3, 11),
        archived=date(2024, 4, 30),
    )
    await _create_closed(
        factory,
        fees="0.00",
        created=datetime(2024, 3, 1, tzinfo=UTC),
        closure=date(2024, 3, 11),
        archived=date(2024, 5, 30),
    )
    # Sem receita e sem arquivamento: rotação nula (regra 2) — não há meses a somar.
    await _create_closed(factory, fees="0.00", closure=date(2024, 3, 11))
    await _refresh()

    result = await _lost_time(client, factory.headers)
    assert result["zero_revenue_lawsuits"] == 2
    assert result["lost_months"] == pytest.approx(5.0)


@pytest.mark.commits
async def test_revenue_ignora_nao_pago_e_interno(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 6: só receita PAGA e não interna conta — lançamento em aberto e interno
    (mesmo pago) deixam o processo com `revenue = 0`, e ele vira tempo perdido."""
    fixtures = await _financial_fixtures(client, factory.headers)
    # Processo A: receita paga de 500 — não é tempo perdido.
    paid_id, paid_customer = await _create_closed(
        factory,
        fees="500.00",
        created=datetime(2024, 3, 1, tzinfo=UTC),
        closure=date(2024, 3, 11),
        archived=date(2024, 4, 30),
    )
    await _add_revenue(
        client,
        factory.headers,
        fixtures,
        lawsuit_id=paid_id,
        customer_id=paid_customer,
        amount="500.00",
    )
    # Processo B: receita em aberto de 700 + interna paga de 900 — revenue = 0.
    ignored_id, ignored_customer = await _create_closed(
        factory,
        fees="0.00",
        created=datetime(2024, 3, 1, tzinfo=UTC),
        closure=date(2024, 3, 11),
        archived=date(2024, 4, 30),
    )
    await _add_revenue(
        client,
        factory.headers,
        fixtures,
        lawsuit_id=ignored_id,
        customer_id=ignored_customer,
        amount="700.00",
        paid=False,
    )
    await _add_revenue(
        client,
        factory.headers,
        fixtures,
        lawsuit_id=ignored_id,
        customer_id=ignored_customer,
        amount="900.00",
        internal=True,
    )
    await _refresh()

    result = await _lost_time(client, factory.headers)
    assert result["zero_revenue_lawsuits"] == 1
    assert result["lost_months"] == pytest.approx(2.0)


@pytest.mark.commits
async def test_filtro_por_resultado_recalcula(client: AsyncClient, factory: LawsuitFactory) -> None:
    """Regra 7: o filtro por resultado recalcula tudo — contagem, média de honorários
    e os ciclos mudam junto com o recorte."""
    await _create_closed(factory, fees="1000.00", closure=date(2024, 3, 1), outcome="GANHO")
    await _create_closed(factory, fees="3000.00", closure=date(2024, 3, 1), outcome="GANHO")
    await _create_closed(factory, fees="8000.00", closure=date(2024, 3, 1), outcome="PERDIDO")
    await _refresh()

    todos = await _time_fees(client, factory.headers)
    assert todos["lawsuits"] == 3
    assert todos["avg_fees"] == pytest.approx(4000.00)

    ganhos = await _time_fees(client, factory.headers, outcome="GANHO")
    assert ganhos["lawsuits"] == 2
    assert ganhos["avg_fees"] == pytest.approx(2000.00)

    perdidos = await _time_fees(client, factory.headers, outcome="PERDIDO")
    assert perdidos["lawsuits"] == 1
    assert perdidos["avg_fees"] == pytest.approx(8000.00)

    # Recorte vazio: médias None ("—" na UI), nunca zero (mesmo idioma da regra 11 da 075).
    vazio = await _time_fees(client, factory.headers, from_="2030-01-01", to="2030-12-31")
    assert vazio["lawsuits"] == 0
    assert vazio["avg_fees"] is None
    assert vazio["avg_monthly_fees"] is None
    assert vazio["cycles"]["prospecting_days"] is None


@pytest.mark.commits
async def test_rentabilidade_por_tipo(client: AsyncClient, factory: LawsuitFactory) -> None:
    """Regra 8: rentabilidade mensal por tipo = média de (`fees_value` ÷ meses de
    duração) dos processos daquele tipo; o filtro por tipo devolve só ele."""
    # Tipo da factory: 6000 em 60 dias (2 meses) → 3000/mês.
    await _create_closed(
        factory,
        fees="6000.00",
        created=datetime(2024, 3, 1, tzinfo=UTC),
        closure=date(2024, 3, 11),
        archived=date(2024, 4, 30),
    )
    # Segundo tipo: 1500 em 90 dias (3 meses) → 500/mês.
    other_type_id, _group_id = await _create_lawsuit_type(client, factory.headers)
    await _create_closed(
        factory,
        fees="1500.00",
        created=datetime(2024, 3, 1, tzinfo=UTC),
        closure=date(2024, 3, 11),
        archived=date(2024, 5, 30),
        lawsuit_type_id=other_type_id,
    )
    await _refresh()

    result = await _by_type(client, factory.headers)
    by_id = {row["lawsuit_type_id"]: row for row in result["types"]}
    assert by_id[factory.type_id]["monthly_profitability"] == pytest.approx(3000.00)
    assert by_id[other_type_id]["monthly_profitability"] == pytest.approx(500.00)

    filtrado = await _by_type(client, factory.headers, lawsuit_type_id=other_type_id)
    assert [row["lawsuit_type_id"] for row in filtrado["types"]] == [other_type_id]


@pytest.mark.commits
async def test_menos_de_5_processos_aviso_de_amostra(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 9: tipo com menos de 5 processos no recorte exibe aviso de amostra
    pequena; com 5 ou mais, não."""
    for _ in range(2):
        await _create_closed(factory, fees="100.00", closure=date(2024, 3, 1))
    other_type_id, _group_id = await _create_lawsuit_type(client, factory.headers)
    for _ in range(5):
        await _create_closed(
            factory, fees="100.00", closure=date(2024, 3, 1), lawsuit_type_id=other_type_id
        )
    await _refresh()

    result = await _by_type(client, factory.headers)
    by_id = {row["lawsuit_type_id"]: row for row in result["types"]}
    assert by_id[factory.type_id]["lawsuits"] == 2
    assert by_id[factory.type_id]["small_sample"] is True
    assert by_id[other_type_id]["lawsuits"] == 5
    assert by_id[other_type_id]["small_sample"] is False


@pytest.mark.commits
async def test_ciclos_por_grupo_lado_a_lado(client: AsyncClient, factory: LawsuitFactory) -> None:
    """Regra 10: o gráfico por grupo mostra os 4 ciclos lado a lado — e a média
    ignora nulos (regra 2 no SQL: quem não tem trânsito não entra na produção)."""
    # Grupo da factory é identificado ANTES de criar o segundo — _factory_group_id
    # assume exatamente um grupo no tenant.
    factory_group_id = await _factory_group_id(client, factory)
    # 30 dias de prospecção, 121 de produção, 122 de execução, 273 de rotação.
    await _create_closed(
        factory,
        fees="1000.00",
        created=datetime(2024, 1, 1, tzinfo=UTC),
        closure=date(2024, 1, 31),
        transit=date(2024, 5, 31),
        archived=date(2024, 9, 30),
    )
    # Sem trânsito nem arquivamento: só prospecção (10 dias) — não zera as outras médias.
    await _create_closed(
        factory,
        fees="1000.00",
        created=datetime(2024, 1, 1, tzinfo=UTC),
        closure=date(2024, 1, 11),
    )
    other_type_id, other_group_id = await _create_lawsuit_type(client, factory.headers)
    await _create_closed(
        factory,
        fees="1000.00",
        created=datetime(2024, 1, 1, tzinfo=UTC),
        closure=date(2024, 1, 11),
        lawsuit_type_id=other_type_id,
    )
    await _refresh()

    result = await _by_group(client, factory.headers)
    by_id = {row["action_group_id"]: row for row in result["groups"]}
    grupo = by_id[factory_group_id]
    assert grupo["lawsuits"] == 2
    assert grupo["cycles"]["prospecting_days"] == pytest.approx(20.0)  # (30+10)/2
    assert grupo["cycles"]["production_days"] == pytest.approx(121.0)  # só o 1º tem trânsito
    assert grupo["cycles"]["execution_days"] == pytest.approx(122.0)
    assert grupo["cycles"]["full_cycle_days"] == pytest.approx(273.0)
    outro = by_id[other_group_id]
    assert outro["cycles"]["prospecting_days"] == pytest.approx(10.0)
    # Regra 2: nenhum processo do grupo tem trânsito/arquivamento → nulo, nunca zero.
    assert outro["cycles"]["production_days"] is None
    assert outro["cycles"]["execution_days"] is None
    assert outro["cycles"]["full_cycle_days"] is None


async def test_sem_acesso_financeiro_recebe_403(
    client: AsyncClient,
    factory: LawsuitFactory,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Regra 11: dupla permissão — Gestor SEM acesso financeiro e Colaborador COM
    acesso são barrados nos 4 endpoints (a aba mostra dinheiro)."""
    gestor_sem_financeiro = await make_user(
        tenant_id=factory.gestor.tenant_id,
        role=UserRole.GESTOR,
        financial_access=FinancialAccess.NONE,
    )
    colaborador_com_financeiro = await make_user(
        tenant_id=factory.gestor.tenant_id,
        role=UserRole.COLABORADOR,
        financial_access=FinancialAccess.FULL,
    )
    for headers in (auth_header(gestor_sem_financeiro), auth_header(colaborador_com_financeiro)):
        for path in (
            "/api/v1/bi/time-fees",
            "/api/v1/bi/time-fees/by-group",
            "/api/v1/bi/time-fees/by-type",
            "/api/v1/bi/time-fees/lost-time",
        ):
            response = await client.get(path, headers=headers)
            assert response.status_code == 403, path


async def test_tenant_a_nao_ve_ciclos_de_tenant_b(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """CLAUDE.md §4: a view barreira embute o filtro de tenant — tenant B não enxerga
    os ciclos de A nem com a view refrescada (matview não tem RLS)."""
    factory_a = await _make_factory(client, make_user, app_session_factory)
    factory_b = await _make_factory(client, make_user, app_session_factory)

    await _create_closed(
        factory_a,
        fees="9000.00",
        created=datetime(2024, 3, 1, tzinfo=UTC),
        closure=date(2024, 3, 11),
        archived=date(2024, 4, 30),
    )
    await _refresh()

    time_fees_b = await _time_fees(client, factory_b.headers)
    assert time_fees_b["lawsuits"] == 0
    assert time_fees_b["avg_fees"] is None

    by_group_b = await _by_group(client, factory_b.headers)
    assert by_group_b["groups"] == []

    lost_time_b = await _lost_time(client, factory_b.headers)
    assert lost_time_b["zero_revenue_lawsuits"] == 0
    assert lost_time_b["lost_months"] == 0
