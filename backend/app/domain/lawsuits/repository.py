import uuid
from collections.abc import Sequence

from sqlalchemy import func, select

from app.core.repository import BaseRepository
from app.domain.customers.models import Customer
from app.domain.lawsuits.models import Lawsuit, LawsuitParty, PartyPole


class LawsuitRepository(BaseRepository[Lawsuit]):
    model = Lawsuit


class LawsuitPartyRepository(BaseRepository[LawsuitParty]):
    model = LawsuitParty

    async def list_for_lawsuit(self, lawsuit_id: uuid.UUID) -> Sequence[tuple[LawsuitParty, str]]:
        """Partes com o nome do contato, na ordem de exibição da regra 7:
        polo (ATIVO → PASSIVO → CONTRARIA → TERCEIRO — ordem natural do enum) e,
        dentro do polo, alfabética."""
        stmt = (
            select(LawsuitParty, Customer.name)
            .join(Customer, Customer.id == LawsuitParty.customer_id)
            .where(LawsuitParty.lawsuit_id == lawsuit_id)
            .order_by(LawsuitParty.pole, Customer.name)
        )
        result = await self.session.execute(stmt)
        return result.tuples().all()

    async def find_duplicate(
        self,
        *,
        lawsuit_id: uuid.UUID,
        customer_id: uuid.UUID,
        pole: PartyPole,
        exclude_id: uuid.UUID | None = None,
    ) -> LawsuitParty | None:
        stmt = select(LawsuitParty).where(
            LawsuitParty.lawsuit_id == lawsuit_id,
            LawsuitParty.customer_id == customer_id,
            LawsuitParty.pole == pole,
        )
        if exclude_id is not None:
            stmt = stmt.where(LawsuitParty.id != exclude_id)
        result = await self.session.scalars(stmt)
        return result.first()

    async def count_for_lawsuit(self, lawsuit_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(LawsuitParty)
            .where(LawsuitParty.lawsuit_id == lawsuit_id)
        )
        return await self.session.scalar(stmt) or 0
