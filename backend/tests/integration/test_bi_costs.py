"""BI: Custos (spec 077).

O custo fixo/marketing/custo por ponto vêm da view materializada bi_cost_allocation
(estática entre refreshes, mesmo padrão das 074/075/076): os testes criam lançamentos
e concluem tarefas pela API e chamam `refresh_bi_costs` direto com a
MIGRATIONS_DATABASE_URL — a fila nunca participa de teste (CLAUDE.md §3). Custo direto,
rateio e clientes novos são tempo real. Cada teste trabalha num tenant próprio
(factory), então o refresh global não contamina vizinhos: a view barreira filtra por
`app.tenant_id`.
"""

import uuid
from calendar import monthrange
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import TypedDict

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.rls import set_tenant_context
from app.domain.users.models import FinancialAccess, UserRole
from app.workers.bi_costs import refresh_bi_costs
from tests.integration.conftest import SeededUser, auth_header
from tests.integration.test_lawsuits import _create_customer, _create_lawsuit
from tests.integration.test_lawsuits_listing import LawsuitFactory, _make_factory
from tests.integration.test_posts import _create_task_type
from tests.integration.test_transactions import (
    _create_account,
    _create_category,
    _create_cost_center,
)

_NOW = datetime.now(UTC)
_TODAY = _NOW.date()
_THIS_MONTH = _TODAY.replace(day=1)
_THIS_MONTH_PARAM = f"{_THIS_MONTH:%Y-%m}"


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
    await refresh_bi_costs(url)


def _this_month_moment() -> datetime:
    """Uma hora atrás, sem nunca cruzar a virada de mês (flaky no dia 1 às 00h)."""
    candidate = _NOW - timedelta(hours=1)
    if candidate.month != _NOW.month:
        return _NOW
    return candidate


class _CostsItemBody(TypedDict):
    lawsuit_id: str
    folder: str | None
    process_number: str | None
    in_progress: bool
    direct_cost: float
    points: int
    points_cost: float | None
    allocated_cost: float


class _CostsBody(TypedDict):
    items: list[_CostsItemBody]
    total_direct: float
    total_allocated: float
    staleness_hint: str
    allocation_note: str


class _CacBody(TypedDict):
    period: str
    marketing_cost: float
    new_customers: int
    cac: float | None
    staleness_hint: str


class _PerPointBody(TypedDict):
    period: str
    fixed_cost: float
    points: int
    cost_per_point: float | None
    staleness_hint: str


async def _costs(client: AsyncClient, headers: dict[str, str], **params: str) -> _CostsBody:
    response = await client.get("/api/v1/bi/costs", params=params, headers=headers)
    assert response.status_code == 200, response.json()
    return response.json()  # type: ignore[no-any-return]


async def _cac(client: AsyncClient, headers: dict[str, str], period: str) -> _CacBody:
    response = await client.get("/api/v1/bi/costs/cac", params={"period": period}, headers=headers)
    assert response.status_code == 200, response.json()
    return response.json()  # type: ignore[no-any-return]


async def _per_point(client: AsyncClient, headers: dict[str, str], period: str) -> _PerPointBody:
    response = await client.get(
        "/api/v1/bi/costs/per-point", params={"period": period}, headers=headers
    )
    assert response.status_code == 200, response.json()
    return response.json()  # type: ignore[no-any-return]


async def _create_lawsuit_with_customer(
    factory: LawsuitFactory, **extra: object
) -> tuple[str, str]:
    """(lawsuit_id, customer_id) — despesa vinculada ao processo exige o cliente
    (spec 056, CHECK `lawsuit_id IS NULL OR customer_id IS NOT NULL`)."""
    customer_id = await _create_customer(
        factory.client, factory.headers, f"Cliente {uuid.uuid4().hex[:8]}"
    )
    lawsuit = await _create_lawsuit(
        factory.client,
        factory.headers,
        user_id=str(factory.gestor.user_id),
        lawsuit_type_id=factory.type_id,
        stage_id=factory.stage_id,
        parties=[{"customer_id": customer_id, "pole": "ATIVO", "is_client": True}],
        **extra,
    )
    return str(lawsuit["id"]), customer_id


@dataclass(frozen=True, slots=True)
class _Contas:
    """As coordenadas contábeis de uma despesa: para onde ela vai no plano de contas.

    Spec 116: os três ids viajavam soltos em catorze chamadas, e `cost_center_id`/
    `account_id` eram literalmente sempre os mesmos — só a categoria mudava. Um objeto
    encurta as catorze e deixa óbvio que os três andam juntos.
    """

    category_id: str
    cost_center_id: str
    account_id: str


async def _add_expense(
    client: AsyncClient,
    headers: dict[str, str],
    contas: _Contas,
    *,
    amount: str,
    due_date: date = _TODAY,
    lawsuit_id: str | None = None,
    customer_id: str | None = None,
    internal: bool = False,
) -> None:
    """Despesa (spec 056) — a competência é o mês de `due_date`; `internal` marca
    lançamento de controle (spec 058, fora do custo)."""
    payload: dict[str, object] = {
        "kind": "DESPESA",
        "debit_account_id": contas.account_id,
        "category_id": contas.category_id,
        "cost_center_id": contas.cost_center_id,
        "amount": amount,
        "due_date": str(due_date),
        "is_internal": internal,
    }
    if lawsuit_id is not None:
        payload["lawsuit_id"] = lawsuit_id
        payload["customer_id"] = customer_id
    response = await client.post("/api/v1/transactions", json=payload, headers=headers)
    assert response.status_code == 201, response.text


async def _complete_task(
    client: AsyncClient,
    factory: LawsuitFactory,
    lawsuit_id: str,
    *,
    reward: int,
    at: datetime | None = None,
) -> None:
    """Tarefa do processo concluída pelo gestor — credita `reward` pontos em
    `post_users.points_earned` na competência de `completed_at` (specs 032/033)."""
    task_type_id = await _create_task_type(client, factory.headers, reward=reward)
    created = await client.post(
        "/api/v1/posts",
        json={
            "lawsuit_id": lawsuit_id,
            "task_type_id": task_type_id,
            "user_ids": [str(factory.gestor.user_id)],
            "scheduled_date": str(_TODAY),
        },
        headers=factory.headers,
    )
    assert created.status_code == 201, created.json()
    payload = {"completed_at": at.isoformat()} if at is not None else {}
    response = await client.post(
        f"/api/v1/posts/{created.json()['id']}/complete", json=payload, headers=factory.headers
    )
    assert response.status_code == 200, response.json()


@pytest.mark.commits
async def test_cac_e_marketing_dividido_por_clientes_novos(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 1: CAC = despesas do grupo 8 (marketing e comercial) ÷ clientes novos
    no período."""
    marketing_id = await _create_category(client, factory.headers, type_="DESPESA", dre_group_id=8)
    cost_center_id = await _create_cost_center(client, factory.headers)
    account_id = await _create_account(client, factory.headers)
    await _add_expense(
        client,
        factory.headers,
        _Contas(marketing_id, cost_center_id, account_id),
        amount="600.00",
    )
    for _ in range(3):
        await _create_customer(client, factory.headers, f"Cliente {uuid.uuid4().hex[:8]}")
    await _refresh()

    result = await _cac(client, factory.headers, _THIS_MONTH_PARAM)
    assert result["marketing_cost"] == pytest.approx(600.00)
    assert result["new_customers"] == 3
    assert result["cac"] == pytest.approx(200.00)


@pytest.mark.commits
async def test_custo_por_ponto_e_custo_fixo_dividido_por_pontos(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 2: custo por ponto = custo fixo do mês ÷ pontos do Taskscore concluídos
    no mês."""
    folha_id = await _create_category(client, factory.headers, type_="DESPESA", dre_group_id=2)
    cost_center_id = await _create_cost_center(client, factory.headers)
    account_id = await _create_account(client, factory.headers)
    await _add_expense(
        client,
        factory.headers,
        _Contas(folha_id, cost_center_id, account_id),
        amount="1000.00",
    )
    lawsuit_id = await factory.create()
    await _complete_task(client, factory, lawsuit_id, reward=8, at=_this_month_moment())
    await _complete_task(client, factory, lawsuit_id, reward=8, at=_this_month_moment())
    await _refresh()

    result = await _per_point(client, factory.headers, _THIS_MONTH_PARAM)
    assert result["fixed_cost"] == pytest.approx(1000.00)
    assert result["points"] == 16
    assert result["cost_per_point"] == pytest.approx(62.50)


@pytest.mark.commits
async def test_custo_fixo_soma_apenas_grupos_2_3_5_7(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 3: custo fixo = grupos DRE 2 (folha), 3 (encargos), 5 (fixas) e 7
    (bancárias) — tributos (4), variáveis (6) e marketing (8) ficam de fora; marketing
    aparece no campo próprio."""
    cost_center_id = await _create_cost_center(client, factory.headers)
    account_id = await _create_account(client, factory.headers)
    for group_id, amount in ((2, "100.00"), (3, "200.00"), (5, "300.00"), (7, "50.00")):
        category_id = await _create_category(
            client, factory.headers, type_="DESPESA", dre_group_id=group_id
        )
        await _add_expense(
            client,
            factory.headers,
            _Contas(category_id, cost_center_id, account_id),
            amount=amount,
        )
    for group_id, amount in ((4, "888.00"), (6, "999.00"), (8, "777.00")):
        category_id = await _create_category(
            client, factory.headers, type_="DESPESA", dre_group_id=group_id
        )
        await _add_expense(
            client,
            factory.headers,
            _Contas(category_id, cost_center_id, account_id),
            amount=amount,
        )
    await _refresh()

    per_point = await _per_point(client, factory.headers, _THIS_MONTH_PARAM)
    assert per_point["fixed_cost"] == pytest.approx(650.00)
    cac = await _cac(client, factory.headers, _THIS_MONTH_PARAM)
    assert cac["marketing_cost"] == pytest.approx(777.00)


async def test_custo_direto_por_lawsuit_id(client: AsyncClient, factory: LawsuitFactory) -> None:
    """Regra 4: custo direto do processo = despesas lançadas com `lawsuit_id` —
    despesa sem processo não entra em nenhum item."""
    category_id = await _create_category(client, factory.headers, type_="DESPESA", dre_group_id=6)
    cost_center_id = await _create_cost_center(client, factory.headers)
    account_id = await _create_account(client, factory.headers)
    lawsuit_a, customer_a = await _create_lawsuit_with_customer(factory)
    lawsuit_b, _customer_b = await _create_lawsuit_with_customer(factory)
    for amount in ("100.00", "50.00"):
        await _add_expense(
            client,
            factory.headers,
            _Contas(category_id, cost_center_id, account_id),
            amount=amount,
            lawsuit_id=lawsuit_a,
            customer_id=customer_a,
        )
    # Despesa avulsa (sem processo) — não pode vazar para nenhum item.
    await _add_expense(
        client,
        factory.headers,
        _Contas(category_id, cost_center_id, account_id),
        amount="999.00",
    )

    result = await _costs(client, factory.headers)
    by_id = {item["lawsuit_id"]: item for item in result["items"]}
    assert by_id[lawsuit_a]["direct_cost"] == pytest.approx(150.00)
    assert by_id[lawsuit_b]["direct_cost"] == pytest.approx(0.00)


@pytest.mark.commits
async def test_custo_alocado_soma_direto_mais_rateio(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 5: custo alocado = custo direto + (pontos das tarefas do processo ×
    custo por ponto do mês). Fixo 800 e 10 pontos → custo por ponto 80, rateio 800."""
    folha_id = await _create_category(client, factory.headers, type_="DESPESA", dre_group_id=2)
    custas_id = await _create_category(client, factory.headers, type_="DESPESA", dre_group_id=6)
    cost_center_id = await _create_cost_center(client, factory.headers)
    account_id = await _create_account(client, factory.headers)
    await _add_expense(
        client,
        factory.headers,
        _Contas(folha_id, cost_center_id, account_id),
        amount="800.00",
    )
    lawsuit_id, customer_id = await _create_lawsuit_with_customer(factory)
    await _add_expense(
        client,
        factory.headers,
        _Contas(custas_id, cost_center_id, account_id),
        amount="100.00",
        lawsuit_id=lawsuit_id,
        customer_id=customer_id,
    )
    await _complete_task(client, factory, lawsuit_id, reward=10, at=_this_month_moment())
    await _refresh()

    result = await _costs(client, factory.headers)
    item = next(i for i in result["items"] if i["lawsuit_id"] == lawsuit_id)
    assert item["direct_cost"] == pytest.approx(100.00)
    assert item["points"] == 10
    assert item["points_cost"] == pytest.approx(800.00)
    assert item["allocated_cost"] == pytest.approx(900.00)


async def test_processo_em_andamento_entra_no_calculo(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 6: diferente das outras abas, processo em andamento entra — custo
    acontece antes do fechamento."""
    category_id = await _create_category(client, factory.headers, type_="DESPESA", dre_group_id=6)
    cost_center_id = await _create_cost_center(client, factory.headers)
    account_id = await _create_account(client, factory.headers)
    # Sem closure_date/transit_date/archived_date: em andamento.
    lawsuit_id, customer_id = await _create_lawsuit_with_customer(factory)
    await _add_expense(
        client,
        factory.headers,
        _Contas(category_id, cost_center_id, account_id),
        amount="50.00",
        lawsuit_id=lawsuit_id,
        customer_id=customer_id,
    )

    result = await _costs(client, factory.headers)
    item = next(i for i in result["items"] if i["lawsuit_id"] == lawsuit_id)
    assert item["in_progress"] is True
    assert item["direct_cost"] == pytest.approx(50.00)
    assert item["allocated_cost"] == pytest.approx(50.00)


@pytest.mark.commits
async def test_mes_sem_pontos_custo_por_ponto_nulo(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 8: mês sem pontos → custo por ponto nulo ("—" na UI), nunca infinito."""
    folha_id = await _create_category(client, factory.headers, type_="DESPESA", dre_group_id=2)
    cost_center_id = await _create_cost_center(client, factory.headers)
    account_id = await _create_account(client, factory.headers)
    await _add_expense(
        client,
        factory.headers,
        _Contas(folha_id, cost_center_id, account_id),
        amount="500.00",
    )
    await _refresh()

    result = await _per_point(client, factory.headers, _THIS_MONTH_PARAM)
    assert result["fixed_cost"] == pytest.approx(500.00)
    assert result["points"] == 0
    assert result["cost_per_point"] is None


async def test_mes_sem_custo_cac_nulo(client: AsyncClient, factory: LawsuitFactory) -> None:
    """Regra 9: mês sem gasto de marketing → CAC nulo, não zero — mesmo com cliente
    novo no período."""
    await _create_customer(client, factory.headers, f"Cliente {uuid.uuid4().hex[:8]}")
    await _refresh()

    result = await _cac(client, factory.headers, _THIS_MONTH_PARAM)
    assert result["marketing_cost"] == 0
    assert result["new_customers"] == 1
    assert result["cac"] is None


@pytest.mark.commits
async def test_interno_e_transferencia_fora_do_custo(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Interno (spec 058, controle) e transferência (movimentação entre contas, spec
    056) nunca entram no custo fixo nem no marketing."""
    folha_id = await _create_category(client, factory.headers, type_="DESPESA", dre_group_id=2)
    cost_center_id = await _create_cost_center(client, factory.headers)
    account_a = await _create_account(client, factory.headers)
    account_b = await _create_account(client, factory.headers)
    await _add_expense(
        client,
        factory.headers,
        _Contas(folha_id, cost_center_id, account_a),
        amount="500.00",
    )
    await _add_expense(
        client,
        factory.headers,
        _Contas(folha_id, cost_center_id, account_a),
        amount="300.00",
        internal=True,
    )
    transferencia = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "TRANSFERENCIA",
            "debit_account_id": account_a,
            "credit_account_id": account_b,
            "amount": "700.00",
            "due_date": str(_TODAY),
        },
        headers=factory.headers,
    )
    assert transferencia.status_code == 201, transferencia.text
    await _refresh()

    result = await _per_point(client, factory.headers, _THIS_MONTH_PARAM)
    assert result["fixed_cost"] == pytest.approx(500.00)


async def test_sem_permissao_dupla_recebe_403(
    client: AsyncClient,
    factory: LawsuitFactory,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Regra 12: dupla permissão — Gestor SEM acesso financeiro e Colaborador COM
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
            "/api/v1/bi/costs",
            "/api/v1/bi/costs/cac",
            "/api/v1/bi/costs/per-point",
            "/api/v1/bi/costs/by-stage",
        ):
            response = await client.get(path, headers=headers)
            assert response.status_code == 403, path


async def test_tenant_a_nao_ve_custos_de_tenant_b(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """CLAUDE.md §4: a view barreira embute o filtro de tenant — tenant B não enxerga
    os custos de A nem com a view refrescada (matview não tem RLS)."""
    factory_a = await _make_factory(client, make_user, app_session_factory)
    factory_b = await _make_factory(client, make_user, app_session_factory)

    folha_id = await _create_category(client, factory_a.headers, type_="DESPESA", dre_group_id=2)
    cost_center_id = await _create_cost_center(client, factory_a.headers)
    account_id = await _create_account(client, factory_a.headers)
    await _add_expense(
        client,
        factory_a.headers,
        _Contas(folha_id, cost_center_id, account_id),
        amount="900.00",
    )
    await _refresh()

    per_point_b = await _per_point(client, factory_b.headers, _THIS_MONTH_PARAM)
    assert per_point_b["fixed_cost"] == 0
    assert per_point_b["cost_per_point"] is None

    cac_b = await _cac(client, factory_b.headers, _THIS_MONTH_PARAM)
    assert cac_b["marketing_cost"] == 0
    assert cac_b["cac"] is None

    costs_b = await _costs(client, factory_b.headers)
    assert costs_b["items"] == []
    assert costs_b["total_allocated"] == 0


async def test_cliente_criado_no_ultimo_dia_do_mes_conta_no_denominador(
    client: AsyncClient,
    factory: LawsuitFactory,
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 1, limite superior da janela.

    `new_customers` comparava `created_at < month_end`, e `month_end` é o ÚLTIMO DIA do
    mês — como `created_at` é timestamp, `< 2026-08-31` quer dizer "antes da meia-noite
    do dia 31" e o último dia inteiro sumia do denominador do CAC, todo mês.

    O bug só se manifestava quando a suíte rodava NO último dia do mês (foi assim que
    apareceu, em 31/08/2026: os dois testes de CAC acima passaram a devolver 0 clientes
    novos). Este teste fixa o dia de propósito, para não depender de quando roda.
    """
    customer_id = await _create_customer(
        client, factory.headers, f"Cliente Virada {uuid.uuid4().hex[:8]}"
    )
    hoje = datetime.now(UTC).date()
    ultimo_dia = date(hoje.year, hoje.month, monthrange(hoje.year, hoje.month)[1])
    # 23h do último dia: o instante que a comparação antiga descartava.
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, factory.gestor.tenant_id)
        await session.execute(
            text("UPDATE customers SET created_at = :quando WHERE id = :id"),
            {"quando": datetime.combine(ultimo_dia, time(23, 0), tzinfo=UTC), "id": customer_id},
        )

    result = await _cac(client, factory.headers, f"{hoje:%Y-%m}")

    assert result["new_customers"] == 1
