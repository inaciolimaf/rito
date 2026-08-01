from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.locations.models import City, State

_DEFAULT_CITY_LIMIT = 20


class StateRepository:
    """Taxonomia global sem tenant_id — não herda `BaseRepository` (cuja generalização
    pressupõe PK `uuid.UUID`, ver `app.core.models.Base`); states/cities usam chave
    natural."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> Sequence[State]:
        result = await self.session.scalars(select(State).order_by(State.name))
        return result.all()


class CityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_filtered(
        self, *, state_code: str, query: str | None, limit: int = _DEFAULT_CITY_LIMIT
    ) -> Sequence[City]:
        """Regra 8: cidade só é selecionável depois do estado — `state_code` não é opcional
        aqui (o endpoint exige `state` na query string)."""
        stmt = select(City).where(City.state_code == state_code).order_by(City.name).limit(limit)
        if query:
            stmt = stmt.where(City.name.ilike(f"%{query}%"))
        return (await self.session.scalars(stmt)).all()
