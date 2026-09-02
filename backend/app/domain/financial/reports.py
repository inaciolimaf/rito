"""DRE e DFC (spec 062) — agregação por grupo DRE (spec 054) sobre `transactions`
(spec 056), sem tabela própria: os dois relatórios são só uma leitura diferente do
mesmo razão, cada um com sua coluna de data (regra 1/2)."""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import ColumnElement, Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.financial.models import (
    DreGroup,
    EntryType,
    FinancialCategory,
    Transaction,
    TransactionKind,
)

ReportRegime = Literal["dre", "dfc"]


@dataclass
class ReportGroupRow:
    dre_group_id: int
    dre_group_name: str
    nature: EntryType
    receita: Decimal
    despesa: Decimal

    @property
    def total(self) -> Decimal:
        return self.receita - self.despesa


@dataclass
class FinancialReport:
    period_start: date
    period_end: date
    rows: list[ReportGroupRow]
    total_receita: Decimal
    total_despesa: Decimal

    @property
    def resultado(self) -> Decimal:
        return self.total_receita - self.total_despesa


def _period_filter(regime: ReportRegime, start: date, end: date) -> ColumnElement[bool]:
    # Regra 1/2: DRE é sempre competência, DFC é sempre pagamento (e exige
    # `payment_date` preenchida) — nenhum dos dois segue o seletor de regime do
    # dashboard (spec 059), que é outra tela.
    if regime == "dfc":
        return and_(
            Transaction.payment_date.is_not(None),
            Transaction.payment_date >= start,
            Transaction.payment_date <= end,
        )
    return and_(Transaction.competence >= start, Transaction.competence <= end)


def _group_totals_query(conditions: list[ColumnElement[bool]]) -> Select[Any]:
    """Receita e despesa somadas por grupo do DRE, numa passada só.

    Os dois `FILTER` no mesmo `GROUP BY` em vez de duas consultas: o DRE precisa das duas
    colunas lado a lado, e somá-las separadamente daria dois planos sobre a mesma tabela. O
    `coalesce` existe porque grupo sem lançamento de um dos tipos devolve NULL, e o DRE
    mostra zero — grupo que existe no plano de contas aparece mesmo vazio.
    """
    is_receita = Transaction.kind == TransactionKind.RECEITA
    is_despesa = Transaction.kind == TransactionKind.DESPESA
    return (
        select(
            DreGroup.id,
            DreGroup.name,
            DreGroup.nature,
            func.coalesce(func.sum(Transaction.amount).filter(is_receita), 0),
            func.coalesce(func.sum(Transaction.amount).filter(is_despesa), 0),
        )
        .select_from(Transaction)
        .join(FinancialCategory, FinancialCategory.id == Transaction.category_id)
        .join(DreGroup, DreGroup.id == FinancialCategory.dre_group_id)
        .where(*conditions)
        .group_by(DreGroup.id, DreGroup.name, DreGroup.nature)
        .order_by(DreGroup.id)
    )


class FinancialReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def group_totals(
        self, *, regime: ReportRegime, start: date, end: date, account_id: uuid.UUID | None
    ) -> list[ReportGroupRow]:
        conditions: list[ColumnElement[bool]] = [
            Transaction.is_internal.is_(False),
            Transaction.kind != TransactionKind.TRANSFERENCIA,
            _period_filter(regime, start, end),
        ]
        if account_id is not None:
            conditions.append(Transaction.debit_account_id == account_id)

        rows = (await self.session.execute(_group_totals_query(conditions))).all()
        return [
            ReportGroupRow(
                dre_group_id=group_id,
                dre_group_name=name,
                nature=nature,
                receita=Decimal(receita),
                despesa=Decimal(despesa),
            )
            for group_id, name, nature, receita, despesa in rows
        ]


async def get_financial_report(
    session: AsyncSession,
    *,
    regime: ReportRegime,
    start: date,
    end: date,
    account_id: uuid.UUID | None,
) -> FinancialReport:
    repository = FinancialReportRepository(session)
    rows = await repository.group_totals(regime=regime, start=start, end=end, account_id=account_id)
    total_receita = sum((row.receita for row in rows), Decimal(0))
    total_despesa = sum((row.despesa for row in rows), Decimal(0))
    return FinancialReport(
        period_start=start,
        period_end=end,
        rows=rows,
        total_receita=total_receita,
        total_despesa=total_despesa,
    )
