import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Row, Select, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.listing import paginate_keyset
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
from app.domain.financial.schemas import TransactionRow
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

    async def usage_count(self, account_id: uuid.UUID) -> int:
        """Quantos lançamentos tocam a conta (spec 101, regras 11-12). Conta os dois
        lados: `debit_account_id` (lançamento comum ou origem de transferência) e
        `credit_account_id` (destino da transferência).

        `is_internal` NÃO é filtrado aqui, ao contrário do saldo: um lançamento interno
        continua sendo uma FK viva para a conta — apagar a conta violaria a constraint do
        mesmo jeito. A regra 9 ignora o interno para CALCULAR dinheiro; a regra 11
        pergunta se existe referência.
        """
        stmt = (
            select(func.count())
            .select_from(Transaction)
            .where(
                or_(
                    Transaction.debit_account_id == account_id,
                    Transaction.credit_account_id == account_id,
                )
            )
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def live_balance_delta(self, account_id: uuid.UUID, *, at: date) -> Decimal:
        """Saldo movimentado da conta até `at`, calculado AO VIVO (spec 101, regra 9).

        Mesma semântica da matview `account_daily_balances` (059) — pagos por
        `payment_date`, `NOT is_internal`, transferência somando no destino e subtraindo
        na origem — mas sem depender do refresh do worker. A view existe para o dashboard
        pagar uma varredura só por TODAS as contas; aqui é uma conta e uma data
        arbitrária, onde a view não serve: ela é cumulativa até o último refresh, e o
        endpoint promete o saldo de agora.

        Não inclui `initial_amount` — o saldo final é `initial_amount + delta`, igual à
        view (que o deixa de fora de propósito, para não invalidar a cada edição do
        saldo inicial).
        """
        paid_and_real = (
            Transaction.payment_date.is_not(None),
            Transaction.payment_date <= at,
            Transaction.is_internal.is_(False),
        )
        debit_side = select(
            func.coalesce(
                func.sum(
                    case(
                        (Transaction.kind == TransactionKind.RECEITA, Transaction.amount),
                        else_=-Transaction.amount,
                    )
                ),
                0,
            )
        ).where(*paid_and_real, Transaction.debit_account_id == account_id)
        credit_side = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            *paid_and_real,
            Transaction.kind == TransactionKind.TRANSFERENCIA,
            Transaction.credit_account_id == account_id,
        )
        out = Decimal((await self.session.execute(debit_side)).scalar_one())
        into = Decimal((await self.session.execute(credit_side)).scalar_one())
        return out + into


@dataclass
class LawsuitFinancialTotals:
    received: Decimal
    to_receive: Decimal
    expenses: Decimal


@dataclass
class TransactionTotals:
    total: Decimal
    balance: Decimal
    expected: Decimal
    # Spec 098, regra 1: quantas linhas o filtro casa. Vem da mesma varredura dos
    # somatórios — a listagem pagina desde a 098 e `len(itens)` passou a ser o tamanho
    # da página, não o do filtro.
    count: int = 0


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

    @staticmethod
    def _filter_conditions(
        *,
        kind: TransactionKind | None,
        customer_id: uuid.UUID | None,
        lawsuit_id: uuid.UUID | None,
        status: str | None,
        due_from: date | None,
        due_to: date | None,
        q: str | None,
        internal: str | None,
    ) -> list[ColumnElement[bool]]:
        """Refatoração 060 (duplicação): condições compartilhadas por `list_filtered` e
        `totals_filtered` — o rodapé da listagem soma no banco com o MESMO filtro da
        página, nunca reduzindo `amount` no cliente (regra do audit numérico)."""
        conditions: list[ColumnElement[bool]] = []
        if kind is not None:
            conditions.append(Transaction.kind == kind)
        if customer_id is not None:
            conditions.append(Transaction.customer_id == customer_id)
        if lawsuit_id is not None:
            conditions.append(Transaction.lawsuit_id == lawsuit_id)
        if status == "paid":
            conditions.append(Transaction.payment_date.is_not(None))
        elif status == "open":
            conditions.append(Transaction.payment_date.is_(None))
        if due_from is not None:
            conditions.append(Transaction.due_date >= due_from)
        if due_to is not None:
            conditions.append(Transaction.due_date <= due_to)
        if q:
            conditions.append(Transaction.description.ilike(f"%{q}%"))
        # Regra 9 (spec 058): filtro padrão é "all" — só filtra quando pedido de propósito.
        if internal == "true":
            conditions.append(Transaction.is_internal.is_(True))
        elif internal == "false":
            conditions.append(Transaction.is_internal.is_(False))
        return conditions

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
        cursor: tuple[date, uuid.UUID] | None = None,
        limit: int = 50,
    ) -> Sequence[TransactionRow]:
        """Spec 098, regra 3: keyset por `(due_date, id)`.

        Até aqui esta listagem não paginava de forma nenhuma — devolvia TODOS os
        lançamentos do escritório, cada um com seis JOINs, e o `total` era o
        `len()` da lista inteira. Com 200 mil lançamentos a rota levava 14 segundos, e o
        `next_cursor: None` do schema estava lá desde a 056 esperando por isto.
        """
        conditions = self._filter_conditions(
            kind=kind,
            customer_id=customer_id,
            lawsuit_id=lawsuit_id,
            status=status,
            due_from=due_from,
            due_to=due_to,
            q=q,
            internal=internal,
        )
        stmt = paginate_keyset(
            self._select_with_names().where(*conditions),
            sort_column=Transaction.due_date,
            id_column=Transaction.id,
            descending=True,
            cursor=cursor,
            limit=limit,
        )
        rows = (await self.session.execute(stmt)).all()
        return [self._row_to_transaction_row(row) for row in rows]

    async def totals_filtered(
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
    ) -> TransactionTotals:
        """Rodapé da listagem (spec 059 regra 9) — somado no banco com o MESMO filtro
        da página (não a página visível), nunca no frontend (auditoria numérica, 060)."""
        conditions = self._filter_conditions(
            kind=kind,
            customer_id=customer_id,
            lawsuit_id=lawsuit_id,
            status=status,
            due_from=due_from,
            due_to=due_to,
            q=q,
            internal=internal,
        )
        is_receita = Transaction.kind == TransactionKind.RECEITA
        is_despesa = Transaction.kind == TransactionKind.DESPESA
        is_open = Transaction.payment_date.is_(None)
        stmt = select(
            func.coalesce(func.sum(Transaction.amount), 0),
            func.coalesce(func.sum(Transaction.amount).filter(is_receita), 0)
            - func.coalesce(func.sum(Transaction.amount).filter(is_despesa), 0),
            func.coalesce(func.sum(Transaction.amount).filter(is_open), 0),
            # Spec 098, regra 1: a CONTAGEM do filtro vem junto dos somatórios, na mesma
            # varredura. Uma query separada só para contar percorreria exatamente as
            # mesmas linhas de novo — e estourava o orçamento de 3 da listagem.
            func.count(),
        ).where(*conditions)
        total, balance, expected, quantidade = (await self.session.execute(stmt)).one()
        return TransactionTotals(
            total=Decimal(total),
            balance=Decimal(balance),
            expected=Decimal(expected),
            count=int(quantidade),
        )

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
