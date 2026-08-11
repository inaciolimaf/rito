import uuid
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

    async def get_by_id(self, alert_id: uuid.UUID) -> IntegrationAlert | None:
        return await self.session.get(IntegrationAlert, alert_id)

    async def list_open(self, *, integration: str | None = None) -> Sequence[IntegrationAlert]:
        stmt = select(IntegrationAlert).where(IntegrationAlert.resolved_at.is_(None))
        if integration is not None:
            stmt = stmt.where(IntegrationAlert.integration == integration)
        stmt = stmt.order_by(IntegrationAlert.created_at.desc())
        return (await self.session.scalars(stmt)).all()

    async def list_filtered(self, *, resolved: bool | None) -> Sequence[IntegrationAlert]:
        """Spec 049, §5: `GET /integrations/alerts?resolved=`. `None` devolve tudo —
        `resolved=false` é o uso documentado no contrato (painel de alertas abertos)."""
        stmt = select(IntegrationAlert).order_by(IntegrationAlert.created_at.desc())
        if resolved is True:
            stmt = stmt.where(IntegrationAlert.resolved_at.is_not(None))
        elif resolved is False:
            stmt = stmt.where(IntegrationAlert.resolved_at.is_(None))
        return (await self.session.scalars(stmt)).all()

    async def get_open_by_code(
        self, *, integration: str, code: str, tenant_id: uuid.UUID | None = None
    ) -> IntegrationAlert | None:
        """Regra 6 da 049 (dedup do alerta crítico de saúde) — mesmo predicado de
        `list_open`, restrito a integração+código+tenant."""
        stmt = select(IntegrationAlert).where(
            IntegrationAlert.resolved_at.is_(None),
            IntegrationAlert.integration == integration,
            IntegrationAlert.code == code,
            IntegrationAlert.tenant_id.is_not_distinct_from(tenant_id),
        )
        result = await self.session.scalars(stmt)
        return result.first()
