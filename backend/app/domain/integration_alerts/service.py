"""Alertas de integração (specs 046 e 049) — a camada que faltava.

Os dois routers que listam alerta (`/integration-alerts` e `/integrations/alerts`) e o
que resolve um falavam direto com o repositório (spec 118, checagem 2). O que estava no
router e é HTTP continua lá: só a leitura e a marcação de resolvido desceram, sem regra
nova — `resolve` segue idempotente e segue commitando apenas quando muda alguma coisa.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.integration_alerts.models import IntegrationAlert
from app.domain.integration_alerts.repository import IntegrationAlertRepository


class IntegrationAlertService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.alerts = IntegrationAlertRepository(session)

    async def list_open(self, *, integration: str | None = None) -> Sequence[IntegrationAlert]:
        return await self.alerts.list_open(integration=integration)

    async def list_filtered(self, *, resolved: bool | None) -> Sequence[IntegrationAlert]:
        return await self.alerts.list_filtered(resolved=resolved)

    async def get(self, alert_id: uuid.UUID) -> IntegrationAlert | None:
        return await self.alerts.get_by_id(alert_id)

    async def resolve(self, alert: IntegrationAlert, *, resolved_by: uuid.UUID) -> IntegrationAlert:
        """Idempotente: reresolver um alerta já resolvido não mexe em quem resolveu nem
        em quando — e não escreve no banco."""
        if alert.resolved_at is None:
            alert.resolved_at = datetime.now(UTC)
            alert.resolved_by = resolved_by
            await self.session.commit()
        return alert
