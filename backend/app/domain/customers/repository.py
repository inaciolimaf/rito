from collections.abc import Sequence

from sqlalchemy import select

from app.core.repository import BaseRepository
from app.domain.customers.models import Customer, MaritalStatus


class MaritalStatusRepository(BaseRepository[MaritalStatus]):
    model = MaritalStatus

    async def list_all(self) -> Sequence[MaritalStatus]:
        result = await self.session.scalars(select(MaritalStatus).order_by(MaritalStatus.id))
        return result.all()


class CustomerRepository(BaseRepository[Customer]):
    model = Customer

    async def get_by_identification(self, identification: str) -> Customer | None:
        result = await self.session.scalars(
            select(Customer).where(Customer.identification == identification)
        )
        return result.first()
