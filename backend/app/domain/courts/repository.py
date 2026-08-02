from collections.abc import Sequence

from sqlalchemy import func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.courts.models import Court, CourtSegment, CourtSystem


class CourtRepository:
    """Taxonomia global sem tenant_id — não herda `BaseRepository` (mesmo motivo de
    `app.domain.locations.repository.StateRepository`: PK aqui é `int`, não `uuid.UUID`)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_filtered(
        self,
        *,
        query: str | None = None,
        segment: CourtSegment | None = None,
        state: str | None = None,
    ) -> Sequence[Court]:
        stmt = select(Court).order_by(Court.name)
        if query:
            # Regra 2: sigla exata (case-insensitive) OU nome parcial sem acento.
            search_pattern = func.concat("%", func.unaccent(func.lower(literal(query))), "%")
            stmt = stmt.where(
                or_(
                    func.lower(Court.code) == query.lower(),
                    func.unaccent(func.lower(Court.name)).ilike(search_pattern),
                )
            )
        if segment is not None:
            stmt = stmt.where(Court.segment == segment)
        if state is not None:
            stmt = stmt.where(Court.state_code == state)
        return (await self.session.scalars(stmt)).all()


class CourtSystemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> Sequence[CourtSystem]:
        return (await self.session.scalars(select(CourtSystem).order_by(CourtSystem.name))).all()
