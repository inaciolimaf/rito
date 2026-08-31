import uuid
from collections.abc import Sequence

from sqlalchemy import func, select, update

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

    async def usage_count(self, origin_id: uuid.UUID) -> int:
        """Quantos contatos usam a origem (spec 101, regra 3). `customers.origin_id` é FK
        NOT NULL desde a 017."""
        from app.domain.customers.models import Customer

        stmt = select(func.count()).select_from(Customer).where(Customer.origin_id == origin_id)
        return int((await self.session.execute(stmt)).scalar_one())

    async def reassign(self, *, from_id: uuid.UUID, to_id: uuid.UUID) -> int:
        """Transferência em lote (spec 101, regra 4) — UPDATE único nos contatos."""
        from app.domain.customers.models import Customer

        result = await self.session.execute(
            update(Customer)
            .where(Customer.origin_id == from_id)
            .values(origin_id=to_id)
            .execution_options(synchronize_session=False)
        )
        return int(result.rowcount)  # type: ignore[attr-defined]  # SQLAlchemy tipa `rowcount` só em `CursorResult`; um UPDATE sempre devolve um.
