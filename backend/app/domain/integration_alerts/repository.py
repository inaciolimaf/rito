from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.integration_alerts.models import IntegrationAlert


class IntegrationAlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, alert: IntegrationAlert) -> IntegrationAlert:
        self.session.add(alert)
        await self.session.flush()
        return alert

    async def list_open(self, *, integration: str | None = None) -> Sequence[IntegrationAlert]:
        stmt = select(IntegrationAlert).where(IntegrationAlert.resolved_at.is_(None))
        if integration is not None:
            stmt = stmt.where(IntegrationAlert.integration == integration)
        stmt = stmt.order_by(IntegrationAlert.created_at.desc())
        return (await self.session.scalars(stmt)).all()
