import uuid
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Row, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.listing import paginate_keyset
from app.core.repository import BaseRepository
from app.domain.customers.models import Customer
from app.domain.dunning.models import DunningAttempt, DunningChannel, DunningRule
from app.domain.dunning.schemas import (
    AgingBucket,
    DebtorTotal,
    OverdueRow,
    OverdueSummary,
)
from app.domain.financial.models import Transaction, TransactionKind
from app.domain.lawsuits.models import Lawsuit

# Regra 2: as 5 faixas de aging, em dias de atraso (today - due_date).
_AGING_RANGES: dict[AgingBucket, tuple[int, int | None]] = {
    "1-15": (1, 15),
    "16-30": (16, 30),
    "31-60": (31, 60),
    "61-90": (61, 90),
    "90+": (91, None),
}


class DunningRuleRepository(BaseRepository[DunningRule]):
    model = DunningRule

    async def list_active(self) -> Sequence[DunningRule]:
        return (
            await self.session.scalars(
                select(DunningRule)
                .where(DunningRule.is_active.is_(True))
                .order_by(DunningRule.days_offset)
            )
        ).all()

    async def list_all(self) -> Sequence[DunningRule]:
        return (
            await self.session.scalars(select(DunningRule).order_by(DunningRule.days_offset))
        ).all()

    async def get_by_offset_channel(
        self, *, days_offset: int, channel: DunningChannel
    ) -> DunningRule | None:
        result = await self.session.scalars(
            select(DunningRule).where(
                DunningRule.days_offset == days_offset, DunningRule.channel == channel
            )
        )
        return result.first()


class DunningAttemptRepository(BaseRepository[DunningAttempt]):
    model = DunningAttempt

    async def exists_for_rule(self, *, transaction_id: uuid.UUID, rule_id: uuid.UUID) -> bool:
        """Regra 4: uma tentativa por regra por lançamento — checado antes de tentar
        enviar (a UNIQUE da migration é o cinto de segurança, não o caminho normal)."""
        result = await self.session.scalars(
            select(DunningAttempt.id).where(
                DunningAttempt.transaction_id == transaction_id,
                DunningAttempt.rule_id == rule_id,
            )
        )
        return result.first() is not None

    async def list_for_transaction(self, transaction_id: uuid.UUID) -> Sequence[DunningAttempt]:
        return (
            await self.session.scalars(
                select(DunningAttempt)
                .where(DunningAttempt.transaction_id == transaction_id)
                .order_by(DunningAttempt.sent_at.desc())
            )
        ).all()


def _overdue_condition(today: date) -> list[ColumnElement[bool]]:
    """Regra 1: atrasado = vencido, em aberto, não interno, RECEITA."""
    return [
        Transaction.due_date < today,
        Transaction.payment_date.is_(None),
        Transaction.is_internal.is_(False),
        Transaction.kind == TransactionKind.RECEITA,
    ]


def _aging_sum(min_days: int, max_days: int | None, today: date) -> ColumnElement[Decimal]:
    conditions: list[ColumnElement[bool]] = [
        Transaction.due_date <= today - timedelta(days=min_days)
    ]
    if max_days is not None:
        conditions.append(Transaction.due_date > today - timedelta(days=max_days + 1))
    return func.coalesce(func.sum(Transaction.amount).filter(*conditions), 0)


class OverdueRepository:
    """Leituras sobre `transactions` para o painel de inadimplência — não é dono da
    tabela (financial/repository.py é), só agrega por cima dela, mesmo padrão de
    `app/domain/financial/dashboard.py`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _select_with_names(self) -> Select[Any]:
        return (
            select(
                Transaction,
                Customer.name,
                Customer.email,
                Customer.cellphone,
                Lawsuit.process_number,
            )
            .outerjoin(Customer, Customer.id == Transaction.customer_id)
            .outerjoin(Lawsuit, Lawsuit.id == Transaction.lawsuit_id)
        )

    @staticmethod
    def _row_to_overdue_row(row: Row[Any]) -> OverdueRow:
        return OverdueRow(
            transaction=row[0],
            customer_name=row[1],
            customer_email=row[2],
            customer_cellphone=row[3],
            process_number=row[4],
        )

    async def get_by_transaction_id(self, transaction_id: uuid.UUID) -> OverdueRow | None:
        stmt = self._select_with_names().where(Transaction.id == transaction_id)
        row = (await self.session.execute(stmt)).first()
        return self._row_to_overdue_row(row) if row is not None else None

    async def list_overdue(
        self,
        *,
        today: date,
        aging: AgingBucket | None,
        customer_id: uuid.UUID | None,
        cursor: tuple[date, uuid.UUID] | None,
        limit: int,
    ) -> tuple[Sequence[OverdueRow], int]:
        conditions = _overdue_condition(today)
        if aging is not None:
            min_days, max_days = _AGING_RANGES[aging]
            conditions.append(Transaction.due_date <= today - timedelta(days=min_days))
            if max_days is not None:
                conditions.append(Transaction.due_date > today - timedelta(days=max_days + 1))
        if customer_id is not None:
            conditions.append(Transaction.customer_id == customer_id)

        count_stmt = select(func.count()).select_from(Transaction).where(*conditions)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = paginate_keyset(
            self._select_with_names().where(*conditions),
            sort_column=Transaction.due_date,
            id_column=Transaction.id,
            descending=False,
            cursor=cursor,
            limit=limit,
        )
        rows = (await self.session.execute(stmt)).all()
        return [self._row_to_overdue_row(row) for row in rows], total

    async def summary(self, *, today: date) -> OverdueSummary:
        """Regra 11: total, por faixa de aging e os 10 maiores devedores — 3 queries
        (o CASE de aging não dá pra combinar com o GROUP BY de devedor na mesma)."""
        base = _overdue_condition(today)
        total = await self.session.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(*base)
        )

        aging_stmt = select(
            *[
                _aging_sum(min_days, max_days, today)
                for min_days, max_days in _AGING_RANGES.values()
            ]
        ).where(*base)
        aging_row = (await self.session.execute(aging_stmt)).one()
        by_aging = {
            bucket: Decimal(value)
            for bucket, value in zip(_AGING_RANGES.keys(), aging_row, strict=True)
        }

        top_stmt = (
            select(Customer.id, Customer.name, func.sum(Transaction.amount).label("total"))
            .join(Customer, Customer.id == Transaction.customer_id)
            .where(*base)
            .group_by(Customer.id, Customer.name)
            .order_by(func.sum(Transaction.amount).desc())
            .limit(10)
        )
        top_rows = (await self.session.execute(top_stmt)).all()
        top_debtors = [
            DebtorTotal(customer_id=row[0], customer_name=row[1], total=Decimal(row[2]))
            for row in top_rows
        ]

        return OverdueSummary(total=Decimal(total or 0), by_aging=by_aging, top_debtors=top_debtors)

    async def list_due_for_rule(self, *, target_due_date: date) -> Sequence[OverdueRow]:
        """Lançamentos elegíveis pra régua (regra 3): `due_date` bate com o alvo do
        offset — independe de já estar "atrasado" (offset negativo é lembrete, ainda
        não venceu). Precisa de `customer_id` pra ter alguém pra quem mandar."""
        stmt = (
            self._select_with_names()
            .where(
                Transaction.due_date == target_due_date,
                Transaction.payment_date.is_(None),
                Transaction.is_internal.is_(False),
                Transaction.kind == TransactionKind.RECEITA,
                Transaction.customer_id.is_not(None),
            )
            .order_by(Transaction.id)
        )
        rows = (await self.session.execute(stmt)).all()
        return [self._row_to_overdue_row(row) for row in rows]
