from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.courts.models import Court, CourtSegment, CourtSystem
from app.domain.courts.repository import CourtRepository, CourtSystemRepository


class CourtService:
    def __init__(self, session: AsyncSession) -> None:
        self.courts = CourtRepository(session)
        self.systems = CourtSystemRepository(session)

    async def list_courts(
        self, *, query: str | None, segment: CourtSegment | None, state: str | None
    ) -> Sequence[Court]:
        return await self.courts.list_filtered(query=query, segment=segment, state=state)

    async def list_systems(self) -> Sequence[CourtSystem]:
        return await self.systems.list_all()
