"""Financeiro: dashboard e fluxo de caixa (spec 059, §8) — os 4 regimes de
visualização com o mesmo dataset, interno e transferência fora dos cálculos,
previsto × realizado, atrasados, saldo por conta (view materializada), fatura do
cartão, refresh da view e orçamento de queries do dashboard."""

from collections.abc import Awaitable, Callable
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.dates import card_cycle_range
from app.core.rls import set_tenant_context
from app.domain.financial.dashboard import get_dashboard_stats
from app.workers.financial_dashboard import refresh_account_daily_balances
from tests.clock import hoje
from tests.integration.conftest import SeededUser
from tests.integration.test_transactions import _fixtures, _make_gestor_full, _receita_payload
from tests.perf import e_plumbing


def _despesa_payload(
    *, category_id: str, cost_center_id: str, account_id: str, **extra: object
) -> dict[str, object]:
    """O vencimento padrão é literal de propósito, e continua certo depois da dívida 41.

    Ele é ÂNCORA, não afirmação sobre o presente: quem o usa consulta um mês explícito
    (`?month=2026-08`) ou paga numa data também literal. Um literal no passado que fica
    no passado para sempre não vence — o que vencia era compará-lo com «hoje».
    """
    payload: dict[str, object] = {
        "kind": "DESPESA",
        "debit_account_id": account_id,
        "category_id": category_id,
        "cost_center_id": cost_center_id,
        "amount": "50.00",
        "due_date": "2026-08-10",
    }
    payload.update(extra)
    return payload


async def _stats(
    client: AsyncClient, headers: dict[str, str], *, regime: str, month: str = "2026-08"
) -> dict[str, float]:
    response = await client.get(
        "/api/v1/transactions/stats",
        params={"month": month, "regime": regime},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body: dict[str, float] = response.json()
    return body


async def _refresh() -> None:
    url = get_settings().migrations_database_url
    assert url is not None
    await refresh_account_daily_balances(url)


async def _create_card_account(
    client: AsyncClient, headers: dict[str, str], *, cycle_day: int = 5, due_day: int = 15
) -> str:
    response = await client.post(
        "/api/v1/bank-accounts",
        json={
            "kind": "CARTAO_CREDITO",
            "name": "Cartão Corporativo",
            "initial_amount": "0",
            "cycle_day": cycle_day,
            "due_day": due_day,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    result: str = response.json()["id"]
    return result


def _vencimento_na_fatura(cycle_day: int, today: date) -> date:
    """Um vencimento que cai na fatura corrente do cartão, seja qual for o «hoje».

    Existe por causa da dívida 41. A versão anterior deste arquivo escrevia
    `due_date="2026-08-20"` à mão e contava com o mês corrente ser agosto de 2026: o
    teste passou até 5 de setembro e virou vermelho **permanente** depois, sem que uma
    linha de produção tivesse mudado. Um teste assim não avisa de regressão — ele mente
    duas vezes, primeiro passando por sorte e depois falhando por calendário.

    A janela vem de `card_cycle_range`, a mesma que a aplicação usa em
    `FinancialDashboardRepository.card_invoice`, alimentada com o «hoje» do escritório
    (`tests.clock.hoje()`, spec 114) — que é o mesmo que o router passa via `Clock`.

    Devolve o MEIO da janela, não uma das pontas: quem afirma que as bordas do ciclo
    entram é `tests/unit/test_card_cycle.py`. Aqui o assunto é «cartão mostra fatura, não
    saldo», e um vencimento no miolo mantém os dois testes falando de coisas diferentes.
    """
    start, end = card_cycle_range(cycle_day, today)
    return start + (end - start) // 2


def _vencimento_fora_da_fatura(cycle_day: int, today: date) -> date:
    """O primeiro dia DEPOIS da fatura corrente — o lançamento que não pode entrar na soma.

    É o contra-exemplo que faz o teste valer alguma coisa: sem ele, uma fatura que
    somasse *tudo* do cartão, ignorando o ciclo, passaria igual.
    """
    _start, end = card_cycle_range(cycle_day, today)
    return end + timedelta(days=1)


async def _pay(
    client: AsyncClient, headers: dict[str, str], transaction_id: str, date_: str
) -> None:
    response = await client.post(
        f"/api/v1/transactions/{transaction_id}/pay",
        json={"payment_date": date_},
        headers=headers,
    )
    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    ("regime", "expected"),
    [
        ("due", (300, 100, 50, 50)),
        ("payment", (0, 0, 50, 50)),
        ("competence", (200, 0, 50, 50)),
        ("cash_flow", (200, 0, 50, 50)),
    ],
)
async def test_quatro_regimes_com_o_mesmo_dataset(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    regime: str,
    expected: tuple[float, float, float, float],
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    receita_id, despesa_id, cost_center_id, account_a, _b = await _fixtures(client, headers)

    # TXN A: vence em agosto, mas foi pago em julho e a competência é setembro — só o
    # regime "due" enxerga como receita de agosto.
    txn_a = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            amount="100.00",
            due_date="2026-08-15",
            competence="2026-09-01",
        ),
        headers=headers,
    )
    assert txn_a.status_code == 201, txn_a.text
    await _pay(client, headers, txn_a.json()["id"], "2026-07-20")

    # TXN B: vence em agosto, competência derivada (agosto), ainda em aberto — conta
    # como previsto em "due"/"competence"/"cash_flow", nunca como realizado.
    txn_b = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            amount="200.00",
            due_date="2026-08-18",
        ),
        headers=headers,
    )
    assert txn_b.status_code == 201, txn_b.text

    # TXN C: despesa paga dentro de agosto — conta em todos os regimes.
    txn_c = await client.post(
        "/api/v1/transactions",
        json=_despesa_payload(
            category_id=despesa_id, cost_center_id=cost_center_id, account_id=account_a
        ),
        headers=headers,
    )
    assert txn_c.status_code == 201, txn_c.text
    await _pay(client, headers, txn_c.json()["id"], "2026-08-11")

    body = await _stats(client, headers, regime=regime)
    income_expected, income_realized, expense_expected, expense_realized = expected
    assert body["income_expected"] == income_expected
    assert body["income_realized"] == income_realized
    assert body["expense_expected"] == expense_expected
    assert body["expense_realized"] == expense_realized


async def test_interno_fora_dos_calculos(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    receita_id, _d, cost_center_id, account_a, _b = await _fixtures(client, headers)

    normal = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            amount="100.00",
            due_date="2026-08-15",
        ),
        headers=headers,
    )
    assert normal.status_code == 201

    internal = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            amount="999.00",
            due_date="2026-08-16",
            is_internal=True,
        ),
        headers=headers,
    )
    assert internal.status_code == 201

    body = await _stats(client, headers, regime="due")
    assert body["income_expected"] == 100


async def test_transferencia_nao_conta_como_receita_nem_despesa(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    _r, _d, _cc, account_a, account_b = await _fixtures(client, headers)

    transfer = await client.post(
        "/api/v1/transactions",
        json={
            "kind": "TRANSFERENCIA",
            "debit_account_id": account_a,
            "credit_account_id": account_b,
            "amount": "500.00",
            "due_date": "2026-08-15",
            "payment_date": "2026-08-11",
        },
        headers=headers,
    )
    assert transfer.status_code == 201, transfer.text

    body = await _stats(client, headers, regime="due")
    assert body["income_expected"] == 0
    assert body["expense_expected"] == 0


async def test_atrasados_excluem_interno(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    receita_id, _d, cost_center_id, account_a, _b = await _fixtures(client, headers)

    overdue = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            amount="150.00",
            due_date="2026-08-01",
        ),
        headers=headers,
    )
    assert overdue.status_code == 201

    overdue_internal = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            amount="777.00",
            due_date="2026-08-02",
            is_internal=True,
        ),
        headers=headers,
    )
    assert overdue_internal.status_code == 201

    body = await _stats(client, headers, regime="due")
    assert body["overdue"] == 150


@pytest.mark.commits
async def test_saldo_por_conta_bate_com_a_view(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    receita_id, _d, cost_center_id, account_a, _b = await _fixtures(client, headers)

    created = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            amount="300.00",
        ),
        headers=headers,
    )
    assert created.status_code == 201
    await _pay(client, headers, created.json()["id"], "2026-08-11")
    await _refresh()

    balances = await client.get("/api/v1/bank-accounts/balances", headers=headers)
    assert balances.status_code == 200, balances.text
    row = next(item for item in balances.json()["items"] if item["account_id"] == account_a)
    assert row["balance"] == 300
    assert row["is_invoice"] is False


@pytest.mark.commits
async def test_view_e_estatica_ate_o_refresh(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    receita_id, _d, cost_center_id, account_a, _b = await _fixtures(client, headers)

    created = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            amount="80.00",
        ),
        headers=headers,
    )
    await _pay(client, headers, created.json()["id"], "2026-08-11")

    before = await client.get("/api/v1/bank-accounts/balances", headers=headers)
    row_before = next(item for item in before.json()["items"] if item["account_id"] == account_a)
    assert row_before["balance"] == 0

    await _refresh()
    after = await client.get("/api/v1/bank-accounts/balances", headers=headers)
    row_after = next(item for item in after.json()["items"] if item["account_id"] == account_a)
    assert row_after["balance"] == 80


CICLO_DO_CARTAO = 5

# As bordas que a dívida 41 mostrou importarem. Nenhuma delas é "hoje": o ponto é
# justamente que a data do teste não pode depender de quando ele roda.
DIAS_DE_BORDA = [
    date(2026, 9, 1),  # dia 1 — antes do fechamento: a fatura corrente abriu no mês anterior
    date(2026, 9, 4),  # véspera do fechamento — o último dia da fatura que está acabando
    date(2026, 9, 5),  # o próprio dia do fechamento — o ciclo novo já começou (regra 5)
    date(2026, 2, 28),  # fim de fevereiro, mês curto — onde o clamp do dia 31 age
    date(2026, 12, 31),  # dia 31 de dezembro — a janela atravessa o ano
]


@pytest.mark.parametrize("cycle_day", [CICLO_DO_CARTAO, 31])
@pytest.mark.parametrize("today", DIAS_DE_BORDA)
def test_vencimento_calculado_cai_na_fatura_em_qualquer_data(cycle_day: int, today: date) -> None:
    """A prova de que a dívida 41 não volta, sem precisar congelar o relógio.

    O projeto não tem `freezegun` — e não vai passar a ter por causa deste teste, porque
    a coisa que precisa ser determinística é a **função de posicionamento**, não o
    processo inteiro. Então o relógio entra por parâmetro: são estas cinco datas de borda
    (dia 1, véspera e dia do fechamento, fim de mês curto, virada de ano) contra os dois
    `cycle_day` que exercitam o clamp da regra 5.
    """
    inicio, fim = card_cycle_range(cycle_day, today)
    assert inicio <= _vencimento_na_fatura(cycle_day, today) <= fim
    assert _vencimento_fora_da_fatura(cycle_day, today) > fim


def test_vencimento_calculado_cai_na_fatura_em_qualquer_dia_do_ano() -> None:
    """O mesmo invariante varrido dia a dia: 366 dias × 31 fechamentos possíveis.

    Cinco bordas escolhidas a dedo provam que quem escreveu o teste pensou nelas; a
    varredura prova que não sobrou nenhuma. É aritmética pura de data, sem banco.
    """
    for offset in range(366):
        today = date(2026, 1, 1) + timedelta(days=offset)
        for cycle_day in range(1, 32):
            inicio, fim = card_cycle_range(cycle_day, today)
            assert inicio <= _vencimento_na_fatura(cycle_day, today) <= fim
            assert _vencimento_fora_da_fatura(cycle_day, today) > fim


async def test_cartao_mostra_fatura_nao_saldo(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 10 (spec 101): cartão de crédito não tem saldo, tem fatura do ciclo corrente.

    As duas datas saem de `hoje()` e do ciclo do próprio cartão — ver `_vencimento_na_fatura`
    e a dívida 41 para o porquê de não haver literal de data aqui.
    """
    _gestor, headers = await _make_gestor_full(make_user)
    _r, despesa_id, cost_center_id, _account_a, _b = await _fixtures(client, headers)
    card_id = await _create_card_account(client, headers, cycle_day=CICLO_DO_CARTAO, due_day=15)
    hoje_do_escritorio = hoje()

    dentro = await client.post(
        "/api/v1/transactions",
        json=_despesa_payload(
            category_id=despesa_id,
            cost_center_id=cost_center_id,
            account_id=card_id,
            amount="220.00",
            due_date=_vencimento_na_fatura(CICLO_DO_CARTAO, hoje_do_escritorio).isoformat(),
        ),
        headers=headers,
    )
    assert dentro.status_code == 201, dentro.text

    # Já é da PRÓXIMA fatura: entra no cartão, não entra nesta soma.
    fora = await client.post(
        "/api/v1/transactions",
        json=_despesa_payload(
            category_id=despesa_id,
            cost_center_id=cost_center_id,
            account_id=card_id,
            amount="900.00",
            due_date=_vencimento_fora_da_fatura(CICLO_DO_CARTAO, hoje_do_escritorio).isoformat(),
        ),
        headers=headers,
    )
    assert fora.status_code == 201, fora.text

    balances = await client.get("/api/v1/bank-accounts/balances", headers=headers)
    row = next(item for item in balances.json()["items"] if item["account_id"] == card_id)
    assert row["is_invoice"] is True
    assert row["balance"] == 220


@pytest.mark.commits
async def test_tenant_a_nao_ve_saldo_de_tenant_b(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor_a, headers_a = await _make_gestor_full(make_user)
    receita_id, _d, cost_center_id, account_a, _b = await _fixtures(client, headers_a)
    created = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            amount="500.00",
        ),
        headers=headers_a,
    )
    await _pay(client, headers_a, created.json()["id"], "2026-08-11")
    await _refresh()

    _gestor_b, headers_b = await _make_gestor_full(make_user)
    balances_b = await client.get("/api/v1/bank-accounts/balances", headers=headers_b)
    assert balances_b.status_code == 200
    assert all(item["account_id"] != account_a for item in balances_b.json()["items"])

    balances_a = await client.get("/api/v1/bank-accounts/balances", headers=headers_a)
    row_a = next(item for item in balances_a.json()["items"] if item["account_id"] == account_a)
    assert row_a["balance"] == 500


@pytest.mark.commits
async def test_dashboard_dentro_do_budget_de_queries(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    gestor, headers = await _make_gestor_full(make_user)
    receita_id, despesa_id, cost_center_id, account_a, _b = await _fixtures(client, headers)
    for index in range(3):
        response = await client.post(
            "/api/v1/transactions",
            json=_receita_payload(
                category_id=receita_id,
                cost_center_id=cost_center_id,
                account_id=account_a,
                amount=f"{10 + index}.00",
                due_date="2026-08-15",
            ),
            headers=headers,
        )
        assert response.status_code == 201
    despesa = await client.post(
        "/api/v1/transactions",
        json=_despesa_payload(
            category_id=despesa_id, cost_center_id=cost_center_id, account_id=account_a
        ),
        headers=headers,
    )
    assert despesa.status_code == 201

    statements: list[str] = []
    async with app_session_factory() as session:
        bind = session.get_bind()

        @event.listens_for(bind, "before_cursor_execute", named=True)
        def count_statements(conn: object, cursor: object, statement: str, **kw: object) -> None:
            if not e_plumbing(statement):
                statements.append(statement)

        async with session.begin():
            await set_tenant_context(session, gestor.tenant_id)
            stats = await get_dashboard_stats(
                session,
                regime="due",
                month=date(2026, 8, 1),
                account_id=None,
                today=hoje(),
            )
            assert stats.income_expected == 33

    assert len(statements) <= 5


async def test_grafico_receitas_x_despesas_por_vencimento(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    receita_id, despesa_id, cost_center_id, account_a, _b = await _fixtures(client, headers)

    receita = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            amount="120.00",
            due_date="2026-08-15",
        ),
        headers=headers,
    )
    assert receita.status_code == 201
    despesa = await client.post(
        "/api/v1/transactions",
        json=_despesa_payload(
            category_id=despesa_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            amount="45.00",
            due_date="2026-08-15",
        ),
        headers=headers,
    )
    assert despesa.status_code == 201

    response = await client.get(
        "/api/v1/transactions/chart",
        params={"month": "2026-08", "group_by": "day"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    day = next(item for item in items if item["period_start"] == "2026-08-15")
    assert day["income"] == 120
    assert day["expense"] == 45


async def test_fluxo_de_caixa_projeta_saldo_dia_a_dia(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    _gestor, headers = await _make_gestor_full(make_user)
    receita_id, _d, cost_center_id, account_a, _b = await _fixtures(client, headers)

    paid = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            amount="200.00",
            due_date="2026-08-11",
        ),
        headers=headers,
    )
    await _pay(client, headers, paid.json()["id"], "2026-08-11")

    open_ = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            amount="80.00",
            due_date="2026-08-14",
        ),
        headers=headers,
    )
    assert open_.status_code == 201

    response = await client.get(
        "/api/v1/transactions/cash-flow",
        params={"from": "2026-08-10", "to": "2026-08-15"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    items = {item["day"]: item for item in response.json()["items"]}
    # Regra 1 (cash_flow): pago em 11/08 conta por payment_date; em aberto em 14/08
    # conta por due_date (projeção) — o saldo acumula os dois na ordem do calendário.
    assert items["2026-08-11"]["balance"] == 200
    assert items["2026-08-14"]["balance"] == 280

    invalid_range = await client.get(
        "/api/v1/transactions/cash-flow",
        params={"from": "2026-08-15", "to": "2026-08-10"},
        headers=headers,
    )
    assert invalid_range.status_code == 422


@pytest.mark.commits
async def test_saldo_da_view_bate_com_soma_direta_no_mesmo_dataset(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Auditoria numérica (refatoração 060, Alvo 1): o saldo que a view materializada
    devolve tem que bater, ao centavo, com uma SOMA DIRETA em `transactions` — feita
    aqui por SQL cru, sem passar pelo mesmo código de produção que está sendo
    auditado (senão um bug no cálculo apareceria idêntico dos dois lados)."""
    gestor, headers = await _make_gestor_full(make_user)
    receita_id, despesa_id, cost_center_id, account_a, _b = await _fixtures(client, headers)

    # Valores "feios" de propósito — dízimas e centavos que forçam arredondamento.
    amounts = [
        ("RECEITA", "1234.57"),
        ("DESPESA", "333.33"),
        ("RECEITA", "0.01"),
        ("DESPESA", "999.99"),
    ]
    for kind, amount in amounts:
        payload = (
            _receita_payload(
                category_id=receita_id,
                cost_center_id=cost_center_id,
                account_id=account_a,
                amount=amount,
            )
            if kind == "RECEITA"
            else _despesa_payload(
                category_id=despesa_id,
                cost_center_id=cost_center_id,
                account_id=account_a,
                amount=amount,
            )
        )
        created = await client.post("/api/v1/transactions", json=payload, headers=headers)
        assert created.status_code == 201, created.text
        await _pay(client, headers, created.json()["id"], "2026-08-11")
    await _refresh()

    balances = await client.get("/api/v1/bank-accounts/balances", headers=headers)
    row = next(item for item in balances.json()["items"] if item["account_id"] == account_a)

    async with app_session_factory() as session:
        await set_tenant_context(session, gestor.tenant_id)
        direct_sum = await session.scalar(
            text(
                "SELECT COALESCE(SUM(CASE WHEN kind = 'RECEITA' THEN amount ELSE -amount END), 0) "
                "FROM transactions WHERE debit_account_id = CAST(:account_id AS uuid) "
                "AND payment_date IS NOT NULL AND NOT is_internal"
            ),
            {"account_id": account_a},
        )

    assert row["balance"] == float(direct_sum)


async def test_parcela_que_vence_hoje_no_fuso_do_escritorio_nao_esta_vencida(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Spec 114, regra 3 aplicada ao dinheiro: «atrasado» é `due_date < hoje`, e o hoje
    é o do escritório.

    Este é o caso que a spec usa para explicar por que o defeito custava caro: uma
    parcela que vence HOJE aparecia como vencida durante as horas em que o processo (UTC)
    já tinha virado o dia e o escritório (`America/Sao_Paulo`, o fuso em que as fixtures
    criam a conta) ainda não. Três horas por noite, todo dia, o cliente via cobrança
    indevida no painel.

    O teste roda no mês da parcela para não depender do mês corrente, e usa
    `tests.clock.hoje()` — o mesmo «hoje» que a aplicação agora enxerga.
    """
    _gestor, headers = await _make_gestor_full(make_user)
    receita_id, _d, cost_center_id, account_a, _b = await _fixtures(client, headers)

    vence_hoje = hoje()
    resposta = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id,
            cost_center_id=cost_center_id,
            account_id=account_a,
            amount="500.00",
            due_date=vence_hoje.isoformat(),
        ),
        headers=headers,
    )
    assert resposta.status_code == 201, resposta.text

    body = await _stats(client, headers, regime="due", month=f"{vence_hoje:%Y-%m}")
    # Vence hoje ainda não venceu. Se este número for 500, o servidor virou o dia antes
    # do escritório — que é exatamente o bug da spec 114.
    assert body["overdue"] == 0
