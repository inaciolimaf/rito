from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import BaseRepository
from app.domain.financial.models import (
    AccountKind,
    BankAccount,
    CostCenter,
    DreGroup,
    EntryType,
    FinancialCategory,
    FinancialInstitution,
)


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
