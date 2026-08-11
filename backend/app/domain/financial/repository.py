import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Row, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.repository import BaseRepository
from app.domain.customers.models import Customer
from app.domain.financial.models import (
    AccountKind,
    BankAccount,
    CostCenter,
    DreGroup,
    EntryType,
    FinancialCategory,
    FinancialInstitution,
    Transaction,
    TransactionKind,
    TransactionSeries,
)
from app.domain.users.models import User


class DreGroupRepository:
    """Leitura da tabela global de grupos DRE (sem tenant/RLS) — mesmo padrão de
    `HolidayRepository` (spec 038)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> Sequence[DreGroup]:
        return (await self.session.scalars(select(DreGroup).order_by(DreGroup.id))).all()

    async def get_by_id(self, id_: int) -> DreGroup | None:
        return await self.session.get(DreGroup, id_)


class FinancialCategoryRepository(BaseRepository[FinancialCategory]):
    model = FinancialCategory

    async def get_by_name(self, name: str) -> FinancialCategory | None:
        result = await self.session.scalars(
            select(FinancialCategory).where(
                func.unaccent(func.lower(FinancialCategory.name)) == func.unaccent(func.lower(name))
            )
        )
        return result.first()

    async def list_filtered(
        self,
        *,
        type_: EntryType | None = None,
        dre_group_id: int | None = None,
        is_active: bool | None = None,
        query: str | None = None,
    ) -> Sequence[FinancialCategory]:
        stmt = select(FinancialCategory).order_by(FinancialCategory.name)
        if type_ is not None:
            stmt = stmt.where(FinancialCategory.type == type_)
        if dre_group_id is not None:
            stmt = stmt.where(FinancialCategory.dre_group_id == dre_group_id)
        if is_active is not None:
            stmt = stmt.where(FinancialCategory.is_active.is_(is_active))
        if query:
            stmt = stmt.where(FinancialCategory.name.ilike(f"%{query}%"))
        return (await self.session.scalars(stmt)).all()


class CostCenterRepository(BaseRepository[CostCenter]):
    model = CostCenter

    async def get_by_name(self, name: str) -> CostCenter | None:
        result = await self.session.scalars(
            select(CostCenter).where(
                func.unaccent(func.lower(CostCenter.name)) == func.unaccent(func.lower(name))
            )
        )
        return result.first()

    async def list_filtered(
        self, *, is_active: bool | None = None, query: str | None = None
    ) -> Sequence[CostCenter]:
        stmt = select(CostCenter).order_by(CostCenter.name)
        if is_active is not None:
            stmt = stmt.where(CostCenter.is_active.is_(is_active))
        if query:
            stmt = stmt.where(CostCenter.name.ilike(f"%{query}%"))
        return (await self.session.scalars(stmt)).all()


class FinancialInstitutionRepository:
    """Leitura da tabela global de instituições (sem tenant/RLS) — mesmo padrão de
    `DreGroupRepository`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, id_: int) -> FinancialInstitution | None:
        return await self.session.get(FinancialInstitution, id_)

    async def list_filtered(self, *, query: str | None = None) -> Sequence[FinancialInstitution]:
        stmt = select(FinancialInstitution).order_by(FinancialInstitution.name)
        if query:
            stmt = stmt.where(FinancialInstitution.name.ilike(f"%{query}%"))
        return (await self.session.scalars(stmt)).all()


class BankAccountRepository(BaseRepository[BankAccount]):
    model = BankAccount

    async def get_by_name(self, name: str) -> BankAccount | None:
        result = await self.session.scalars(
            select(BankAccount).where(
                func.unaccent(func.lower(BankAccount.name)) == func.unaccent(func.lower(name))
            )
        )
        return result.first()

    async def list_filtered(
        self, *, kind: AccountKind | None = None, is_active: bool | None = None
    ) -> Sequence[BankAccount]:
        stmt = select(BankAccount).order_by(BankAccount.name)
        if kind is not None:
            stmt = stmt.where(BankAccount.kind == kind)
        if is_active is not None:
            stmt = stmt.where(BankAccount.is_active.is_(is_active))
        return (await self.session.scalars(stmt)).all()

    async def get_default(self) -> BankAccount | None:
        result = await self.session.scalars(
            select(BankAccount).where(
                BankAccount.is_default.is_(True), BankAccount.is_active.is_(True)
            )
        )
        return result.first()


@dataclass
class TransactionRow:
    transaction: Transaction
    user_name: str
    debit_account_name: str | None
    credit_account_name: str | None
    category_name: str | None
    cost_center_name: str | None
    customer_name: str | None


@dataclass
class LawsuitFinancialTotals:
    received: Decimal
    to_receive: Decimal
    expenses: Decimal


class TransactionRepository(BaseRepository[Transaction]):
    model = Transaction

    def _select_with_names(self) -> Select[Any]:
        # Any: Select composto de Transaction + 6 nomes resolvidos por JOIN — mesmo
        # padrão de Select[Any] já aprovado em lawsuits/listing.py::_board_select.
        debit = aliased(BankAccount)
        credit = aliased(BankAccount)
        return (
            select(
                Transaction,
                User.name,
                debit.name,
                credit.name,
                FinancialCategory.name,
                CostCenter.name,
                Customer.name,
            )
            .join(User, User.id == Transaction.user_id)
            .outerjoin(debit, debit.id == Transaction.debit_account_id)
            .outerjoin(credit, credit.id == Transaction.credit_account_id)
            .outerjoin(FinancialCategory, FinancialCategory.id == Transaction.category_id)
            .outerjoin(CostCenter, CostCenter.id == Transaction.cost_center_id)
            .outerjoin(Customer, Customer.id == Transaction.customer_id)
        )

    @staticmethod
    def _row_to_transaction_row(row: Row[Any]) -> TransactionRow:
        return TransactionRow(
            transaction=row[0],
            user_name=row[1],
            debit_account_name=row[2],
            credit_account_name=row[3],
            category_name=row[4],
            cost_center_name=row[5],
            customer_name=row[6],
        )

    async def get_by_id_detail(self, id_: uuid.UUID) -> TransactionRow | None:
        stmt = self._select_with_names().where(Transaction.id == id_)
        row = (await self.session.execute(stmt)).first()
        return self._row_to_transaction_row(row) if row is not None else None

    async def list_filtered(
        self,
        *,
        kind: TransactionKind | None = None,
        customer_id: uuid.UUID | None = None,
        lawsuit_id: uuid.UUID | None = None,
        status: str | None = None,
        due_from: date | None = None,
        due_to: date | None = None,
        q: str | None = None,
        internal: str | None = None,
    ) -> Sequence[TransactionRow]:
        stmt = self._select_with_names().order_by(Transaction.due_date.desc(), Transaction.id)
        if kind is not None:
            stmt = stmt.where(Transaction.kind == kind)
        if customer_id is not None:
            stmt = stmt.where(Transaction.customer_id == customer_id)
        if lawsuit_id is not None:
            stmt = stmt.where(Transaction.lawsuit_id == lawsuit_id)
        if status == "paid":
            stmt = stmt.where(Transaction.payment_date.is_not(None))
        elif status == "open":
            stmt = stmt.where(Transaction.payment_date.is_(None))
        if due_from is not None:
            stmt = stmt.where(Transaction.due_date >= due_from)
        if due_to is not None:
            stmt = stmt.where(Transaction.due_date <= due_to)
        if q:
            stmt = stmt.where(Transaction.description.ilike(f"%{q}%"))
        # Regra 9 (spec 058): filtro padrão é "all" — só filtra quando pedido de propósito.
        if internal == "true":
            stmt = stmt.where(Transaction.is_internal.is_(True))
        elif internal == "false":
            stmt = stmt.where(Transaction.is_internal.is_(False))
        rows = (await self.session.execute(stmt)).all()
        return [self._row_to_transaction_row(row) for row in rows]

    async def lawsuit_financial_totals(self, lawsuit_id: uuid.UUID) -> LawsuitFinancialTotals:
        """Regra 11 (spec 056): alimenta o painel financeiro do processo (spec 024).
        `received`/`expenses` só contam o que foi PAGO; `to_receive` é RECEITA aberta.
        Regra 1 (spec 058): lançamento interno nunca entra nesses agregados — é
        informação de gestão, não caixa (`NOT is_internal` em todos os filtros)."""
        paid_receita = func.coalesce(
            func.sum(Transaction.amount).filter(
                Transaction.kind == TransactionKind.RECEITA,
                Transaction.payment_date.is_not(None),
                Transaction.is_internal.is_(False),
            ),
            0,
        )
        open_receita = func.coalesce(
            func.sum(Transaction.amount).filter(
                Transaction.kind == TransactionKind.RECEITA,
                Transaction.payment_date.is_(None),
                Transaction.is_internal.is_(False),
            ),
            0,
        )
        paid_despesa = func.coalesce(
            func.sum(Transaction.amount).filter(
                Transaction.kind == TransactionKind.DESPESA,
                Transaction.payment_date.is_not(None),
                Transaction.is_internal.is_(False),
            ),
            0,
        )
        stmt = select(paid_receita, open_receita, paid_despesa).where(
            Transaction.lawsuit_id == lawsuit_id
        )
        received, to_receive, expenses = (await self.session.execute(stmt)).one()
        return LawsuitFinancialTotals(received=received, to_receive=to_receive, expenses=expenses)

    async def list_by_series(self, series_id: uuid.UUID) -> Sequence[Transaction]:
        stmt = (
            select(Transaction)
            .where(Transaction.series_id == series_id)
            .order_by(Transaction.due_date, Transaction.installment_number)
        )
        return (await self.session.scalars(stmt)).all()

    async def latest_in_series(self, series_id: uuid.UUID) -> Transaction | None:
        """A ocorrência mais recente por vencimento — serve de molde (categoria, centro
        de custo, conta, valor) pras próximas ocorrências que o worker gerar, refletindo
        edições feitas via `PUT /transaction-series/{id}` (regra 7)."""
        stmt = (
            select(Transaction)
            .where(Transaction.series_id == series_id)
            .order_by(Transaction.due_date.desc())
            .limit(1)
        )
        return (await self.session.scalars(stmt)).first()

    async def first_due_date_in_series(self, series_id: uuid.UUID) -> date | None:
        stmt = select(func.min(Transaction.due_date)).where(Transaction.series_id == series_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()


class TransactionSeriesRepository(BaseRepository[TransactionSeries]):
    model = TransactionSeries

    async def list_active_recurring(self) -> Sequence[TransactionSeries]:
        """Séries de recorrência (não-parceladas) ativas do tenant — o worker mensal
        (regra 4, spec 057) varre só estas."""
        stmt = select(TransactionSeries).where(
            TransactionSeries.is_installment.is_(False), TransactionSeries.is_active.is_(True)
        )
        return (await self.session.scalars(stmt)).all()
