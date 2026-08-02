from collections.abc import Sequence

from sqlalchemy import func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.courts.models import Court, CourtSegment, CourtSystem, CourtSystemLink


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

    async def get_by_code(self, code: str) -> Court | None:
        result = await self.session.scalars(select(Court).where(Court.code == code))
        return result.first()

    async def is_system_compatible(self, *, court_id: int, system_id: int) -> bool:
        """Regra 8 (spec 022): um tribunal com algum vínculo cadastrado só aceita um dos
        sistemas vinculados; um tribunal sem nenhum vínculo (a maioria — spec 021,
        Descobertas) não restringe o sistema."""
        linked_systems = (
            await self.session.scalars(
                select(CourtSystemLink.system_id).where(CourtSystemLink.court_id == court_id)
            )
        ).all()
        if not linked_systems:
            return True
        return system_id in linked_systems


class CourtSystemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> Sequence[CourtSystem]:
        return (await self.session.scalars(select(CourtSystem).order_by(CourtSystem.name))).all()
