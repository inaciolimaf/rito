"""Dashboard financeiro e fluxo de caixa (spec 059).

Cards (`/transactions/stats`) em 3 queries (regra de orçamento do plano de testes:
≤ 5 statements — o repositório soma mais 2 pra buscar as contas e os saldos): uma de
agregados condicionais por regime (previsto/realizado de receita e despesa), uma de
atrasados e duas de saldo (agora e no fim do mês anterior, via
`account_daily_balances_visible` — migration 059).

Os 4 regimes (regra 1) só mudam **qual coluna de data filtra o período** — `payment`/
`due`/`competence` filtram direto; `cash_flow` é híbrido: pago conta por `payment_date`,
em aberto conta por `due_date` (projeção). Lançamento interno nunca entra (regra 2,
mesmo filtro `NOT is_internal` de `ix_tx_effective`/`lawsuit_financial_totals`) e
transferência nunca conta como receita/despesa (regra 3 — o filtro por `kind` já
exclui `TRANSFERENCIA` dos agregados de receita/despesa/atrasados)."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import ColumnElement, Date, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dates import card_cycle_range, next_month_start
from app.core.materialized_view import MATERIALIZED_VIEWS
from app.domain.financial.models import (
    AccountKind,
    BankAccount,
    Transaction,
    TransactionKind,
    account_daily_balances,
)

Regime = Literal["payment", "due", "competence", "cash_flow"]
ChartGroupBy = Literal["day", "week"]

_BALANCE_VIEW = next(
    spec for spec in MATERIALIZED_VIEWS if spec.view_name == "account_daily_balances"
)


@dataclass
class DashboardStats:
    balance: Decimal
    balance_previous: Decimal
    income_expected: Decimal
    income_realized: Decimal
    expense_expected: Decimal
    expense_realized: Decimal
    overdue: Decimal
    # Regra 11 + refatoração 060 (Alvo 2: "métrica de defasagem exposta na UI") — o
    # texto vem do registro central de views, não de uma string solta no frontend.
    balance_staleness_hint: str = _BALANCE_VIEW.staleness_hint()


@dataclass
class ChartPoint:
    period_start: date
    income: Decimal
    expense: Decimal


@dataclass
class CashFlowPoint:
    day: date
    income: Decimal
    expense: Decimal
    balance: Decimal


@dataclass
class AccountBalanceRow:
    account: BankAccount
    balance: Decimal
    is_invoice: bool


def _period_filter(regime: Regime, start: date, end_exclusive: date) -> ColumnElement[bool]:
    if regime == "cash_flow":
        # Regra 1 (cash_flow): pago conta por payment_date, em aberto conta por
        # due_date — é uma projeção, não um recorte por uma única coluna.
        return or_(
            and_(
                Transaction.payment_date.is_not(None),
                Transaction.payment_date >= start,
                Transaction.payment_date < end_exclusive,
            ),
            and_(
                Transaction.payment_date.is_(None),
                Transaction.due_date >= start,
                Transaction.due_date < end_exclusive,
            ),
        )
    if regime == "payment":
        return and_(Transaction.payment_date >= start, Transaction.payment_date < end_exclusive)
    if regime == "due":
        return and_(Transaction.due_date >= start, Transaction.due_date < end_exclusive)
    return and_(Transaction.competence >= start, Transaction.competence < end_exclusive)


class FinancialDashboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def period_totals(
        self, *, regime: Regime, start: date, end_exclusive: date, account_id: uuid.UUID | None
    ) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        """(previsto receita, realizado receita, previsto despesa, realizado despesa)
        numa única query com 4 SUM(...) FILTER condicionais (regra 4: previsto = todos
        do período; realizado = com payment_date preenchida)."""
        base: list[ColumnElement[bool]] = [
            Transaction.is_internal.is_(False),
            _period_filter(regime, start, end_exclusive),
        ]
        if account_id is not None:
            base.append(Transaction.debit_account_id == account_id)
        paid = Transaction.payment_date.is_not(None)
        is_receita = Transaction.kind == TransactionKind.RECEITA
        is_despesa = Transaction.kind == TransactionKind.DESPESA
        stmt = select(
            func.coalesce(func.sum(Transaction.amount).filter(*base, is_receita), 0),
            func.coalesce(func.sum(Transaction.amount).filter(*base, is_receita, paid), 0),
            func.coalesce(func.sum(Transaction.amount).filter(*base, is_despesa), 0),
            func.coalesce(func.sum(Transaction.amount).filter(*base, is_despesa, paid), 0),
        )
        row = (await self.session.execute(stmt)).one()
        income_expected, income_realized, expense_expected, expense_realized = row
        return (
            Decimal(income_expected),
            Decimal(income_realized),
            Decimal(expense_expected),
            Decimal(expense_realized),
        )

    async def overdue_total(self, *, account_id: uuid.UUID | None, today: date) -> Decimal:
        """Regra 5: due_date < hoje e payment_date nulo, excluindo internos —
        independente do regime escolhido (atrasado é sempre por vencimento).

        `today` é o do escritório (spec 114): "atrasado" é a pergunta em que o fuso mais
        custa dinheiro — uma parcela que vence hoje aparecia como vencida durante as
        horas em que o servidor já tinha virado o dia e o escritório não.
        """
        conditions: list[ColumnElement[bool]] = [
            Transaction.is_internal.is_(False),
            Transaction.due_date < today,
            Transaction.payment_date.is_(None),
        ]
        if account_id is not None:
            conditions.append(Transaction.debit_account_id == account_id)
        value = await self.session.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(*conditions)
        )
        return Decimal(value or 0)

    async def balance_accounts(self, *, account_id: uuid.UUID | None) -> Sequence[BankAccount]:
        """Regra 7: cartão de crédito não entra no saldo total — só contas de saldo."""
        stmt = select(BankAccount).where(
            BankAccount.is_active.is_(True), BankAccount.kind != AccountKind.CARTAO_CREDITO
        )
        if account_id is not None:
            stmt = stmt.where(BankAccount.id == account_id)
        return (await self.session.scalars(stmt)).all()

    async def deltas_as_of(
        self, account_ids: Sequence[uuid.UUID], at: date
    ) -> dict[uuid.UUID, Decimal]:
        """A última linha (dia mais recente ≤ `at`) de cada conta, via `DISTINCT ON`
        — uma query cobre N contas (regra 6: saldo vem da view materializada)."""
        if not account_ids:
            return {}
        stmt = (
            select(account_daily_balances.c.account_id, account_daily_balances.c.balance_delta)
            .distinct(account_daily_balances.c.account_id)
            .where(
                account_daily_balances.c.account_id.in_(account_ids),
                account_daily_balances.c.day <= at,
            )
            .order_by(account_daily_balances.c.account_id, account_daily_balances.c.day.desc())
        )
        rows = (await self.session.execute(stmt)).all()
        return {row.account_id: Decimal(row.balance_delta) for row in rows}

    async def chart_series(
        self,
        *,
        start: date,
        end_exclusive: date,
        group_by: ChartGroupBy,
        account_id: uuid.UUID | None,
    ) -> list[ChartPoint]:
        """Regra do ADVBOX: "Receitas x Despesas por vencimento" — sempre due_date,
        independente do regime do dashboard (o gráfico é fixo)."""
        conditions: list[ColumnElement[bool]] = [
            Transaction.is_internal.is_(False),
            Transaction.kind != TransactionKind.TRANSFERENCIA,
            Transaction.due_date >= start,
            Transaction.due_date < end_exclusive,
        ]
        if account_id is not None:
            conditions.append(Transaction.debit_account_id == account_id)
        bucket = (
            func.date_trunc("week", Transaction.due_date).cast(Date)
            if group_by == "week"
            else Transaction.due_date
        )
        is_receita = Transaction.kind == TransactionKind.RECEITA
        is_despesa = Transaction.kind == TransactionKind.DESPESA
        stmt = (
            select(
                bucket.label("bucket"),
                func.coalesce(func.sum(Transaction.amount).filter(is_receita), 0),
                func.coalesce(func.sum(Transaction.amount).filter(is_despesa), 0),
            )
            .where(*conditions)
            .group_by("bucket")
            .order_by("bucket")
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            ChartPoint(period_start=bucket_start, income=Decimal(income), expense=Decimal(expense))
            for bucket_start, income, expense in rows
        ]

    async def cash_flow_movements(
        self, *, start: date, end: date, account_id: uuid.UUID | None
    ) -> list[tuple[date, Decimal, Decimal]]:
        """Movimentos diários (pago por `payment_date` + em aberto projetado por
        `due_date`, regra 1/cash_flow) — usados pelo `/transactions/cash-flow` pra
        montar a série de saldo projetado dia a dia."""
        effective_date = func.coalesce(Transaction.payment_date, Transaction.due_date)
        conditions: list[ColumnElement[bool]] = [
            Transaction.is_internal.is_(False),
            Transaction.kind != TransactionKind.TRANSFERENCIA,
            effective_date >= start,
            effective_date <= end,
        ]
        if account_id is not None:
            conditions.append(Transaction.debit_account_id == account_id)
        is_receita = Transaction.kind == TransactionKind.RECEITA
        is_despesa = Transaction.kind == TransactionKind.DESPESA
        stmt = (
            select(
                effective_date.label("day"),
                func.coalesce(func.sum(Transaction.amount).filter(is_receita), 0),
                func.coalesce(func.sum(Transaction.amount).filter(is_despesa), 0),
            )
            .where(*conditions)
            .group_by("day")
            .order_by("day")
        )
        rows = (await self.session.execute(stmt)).all()
        return [(day, Decimal(income), Decimal(expense)) for day, income, expense in rows]

    async def card_invoice(self, account: BankAccount, *, today: date) -> Decimal:
        """Regra 7: fatura do ciclo — soma de DESPESA com vencimento na janela do ciclo
        corrente (`card_cycle_range`, spec 055 regra 5), pago ou não."""
        # garantido pelo CHECK ck_bank_accounts_card_needs_cycle
        assert account.cycle_day is not None
        start, end = card_cycle_range(account.cycle_day, today)
        value = await self.session.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.debit_account_id == account.id,
                Transaction.kind == TransactionKind.DESPESA,
                Transaction.is_internal.is_(False),
                Transaction.due_date >= start,
                Transaction.due_date <= end,
            )
        )
        return Decimal(value or 0)


async def get_dashboard_stats(
    session: AsyncSession,
    *,
    regime: Regime,
    month: date,
    account_id: uuid.UUID | None,
    today: date,
) -> DashboardStats:
    start = month.replace(day=1)
    end_exclusive = next_month_start(start)
    repository = FinancialDashboardRepository(session)

    (
        income_expected,
        income_realized,
        expense_expected,
        expense_realized,
    ) = await repository.period_totals(
        regime=regime, start=start, end_exclusive=end_exclusive, account_id=account_id
    )
    overdue = await repository.overdue_total(account_id=account_id, today=today)

    # Regra 9 (ADVBOX): saldo do card é sempre "agora vs mês anterior" — independente
    # do `month` navegado, que só afeta previsto/realizado/atrasados acima.
    previous_month_end = today.replace(day=1) - timedelta(days=1)
    accounts = await repository.balance_accounts(account_id=account_id)
    account_ids = [account.id for account in accounts]
    deltas_now = await repository.deltas_as_of(account_ids, today)
    deltas_previous = await repository.deltas_as_of(account_ids, previous_month_end)

    balance = sum(
        (account.initial_amount + deltas_now.get(account.id, Decimal(0)) for account in accounts),
        Decimal(0),
    )
    balance_previous = sum(
        (
            account.initial_amount + deltas_previous.get(account.id, Decimal(0))
            for account in accounts
        ),
        Decimal(0),
    )

    return DashboardStats(
        balance=balance,
        balance_previous=balance_previous,
        income_expected=income_expected,
        income_realized=income_realized,
        expense_expected=expense_expected,
        expense_realized=expense_realized,
        overdue=overdue,
    )


async def get_chart_series(
    session: AsyncSession,
    *,
    month: date,
    group_by: ChartGroupBy,
    account_id: uuid.UUID | None,
) -> list[ChartPoint]:
    start = month.replace(day=1)
    end_exclusive = next_month_start(start)
    repository = FinancialDashboardRepository(session)
    return await repository.chart_series(
        start=start, end_exclusive=end_exclusive, group_by=group_by, account_id=account_id
    )


async def get_cash_flow_series(
    session: AsyncSession, *, start: date, end: date, account_id: uuid.UUID | None
) -> list[CashFlowPoint]:
    """Saldo projetado dia a dia (regime cash_flow): parte do saldo real na véspera de
    `start` (view materializada, regra 6) e soma os movimentos diários — pagos e em
    aberto (regra 1) — dia a dia até `end`."""
    repository = FinancialDashboardRepository(session)
    accounts = await repository.balance_accounts(account_id=account_id)
    account_ids = [account.id for account in accounts]
    deltas = await repository.deltas_as_of(account_ids, start - timedelta(days=1))
    running_balance = sum(
        (account.initial_amount + deltas.get(account.id, Decimal(0)) for account in accounts),
        Decimal(0),
    )

    movements = await repository.cash_flow_movements(start=start, end=end, account_id=account_id)
    by_day = {day: (income, expense) for day, income, expense in movements}

    points: list[CashFlowPoint] = []
    day = start
    while day <= end:
        income, expense = by_day.get(day, (Decimal(0), Decimal(0)))
        running_balance += income - expense
        points.append(
            CashFlowPoint(day=day, income=income, expense=expense, balance=running_balance)
        )
        day += timedelta(days=1)
    return points


async def get_account_balances(
    session: AsyncSession, *, account_id: uuid.UUID | None, today: date
) -> list[AccountBalanceRow]:
    """Regra 7: cartão de crédito mostra a fatura do ciclo, não saldo — as duas
    entram na mesma lista pro card `AccountBalanceRow` do front, com `is_invoice`
    dizendo qual rótulo usar."""
    repository = FinancialDashboardRepository(session)
    stmt_conditions: list[ColumnElement[bool]] = [BankAccount.is_active.is_(True)]
    if account_id is not None:
        stmt_conditions.append(BankAccount.id == account_id)
    stmt = select(BankAccount).where(*stmt_conditions).order_by(BankAccount.name)
    accounts = (await session.scalars(stmt)).all()

    non_card_ids = [
        account.id for account in accounts if account.kind != AccountKind.CARTAO_CREDITO
    ]
    deltas = await repository.deltas_as_of(non_card_ids, today)

    rows: list[AccountBalanceRow] = []
    for account in accounts:
        if account.kind == AccountKind.CARTAO_CREDITO:
            invoice = await repository.card_invoice(account, today=today)
            rows.append(AccountBalanceRow(account=account, balance=invoice, is_invoice=True))
        else:
            balance = account.initial_amount + deltas.get(account.id, Decimal(0))
            rows.append(AccountBalanceRow(account=account, balance=balance, is_invoice=False))
    return rows
