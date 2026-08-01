from collections.abc import Sequence

from sqlalchemy import func, select

from app.core.repository import BaseRepository
from app.domain.customer_origins.models import CustomerOrigin


class CustomerOriginRepository(BaseRepository[CustomerOrigin]):
    model = CustomerOrigin

    async def get_by_name(self, name: str) -> CustomerOrigin | None:
        result = await self.session.scalars(
            select(CustomerOrigin).where(
                func.unaccent(func.lower(CustomerOrigin.name)) == func.unaccent(func.lower(name))
            )
        )
        return result.first()

    async def list_filtered(
        self, *, is_active: bool | None = None, query: str | None = None
    ) -> Sequence[CustomerOrigin]:
        stmt = select(CustomerOrigin).order_by(CustomerOrigin.name)
        if is_active is not None:
            stmt = stmt.where(CustomerOrigin.is_active.is_(is_active))
        if query:
            stmt = stmt.where(CustomerOrigin.name.ilike(f"%{query}%"))
        return (await self.session.scalars(stmt)).all()
