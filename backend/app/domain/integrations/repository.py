from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.integrations.models import IntegrationHealth


class IntegrationHealthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, health: IntegrationHealth) -> IntegrationHealth:
        self.session.add(health)
        await self.session.flush()
        return health

    async def list_recent(self, integration: str, *, limit: int) -> Sequence[IntegrationHealth]:
        """Mais recentes primeiro — regra 6 da 049 usa `limit=2` pra achar duas
        verificações seguidas; o painel de status usa uma janela maior (24 h)."""
        stmt = (
            select(IntegrationHealth)
            .where(IntegrationHealth.integration == integration)
            .order_by(IntegrationHealth.checked_at.desc())
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        return result.all()

    async def list_since(self, integration: str, *, since: datetime) -> Sequence[IntegrationHealth]:
        stmt = (
            select(IntegrationHealth)
            .where(
                IntegrationHealth.integration == integration, IntegrationHealth.checked_at >= since
            )
            .order_by(IntegrationHealth.checked_at.desc())
        )
        result = await self.session.scalars(stmt)
        return result.all()
