"""Métricas de captura e alerta de taxa de vínculo automático (spec 049, §7-8).

Separado de `service.py` (listagem/leitura/export) porque é outra
responsabilidade: aqui é leitura agregada + a regra de negócio do alerta de
taxa baixa, chamada pelo job diário (um por tenant, mesmo padrão de
`MovementSyncService.sync_due` da 047).
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.integration_alerts.models import IntegrationAlert
from app.domain.integration_alerts.repository import IntegrationAlertRepository
from app.domain.publications.repository import PublicationRepository

METRICS_PERIOD_DAYS_DEFAULT = 7
AUTO_LINK_RATE_THRESHOLD = 0.70  # regra 8
_LOW_LINK_RATE_CODE = "low_auto_link_rate"


@dataclass
class PublicationMetrics:
    period_days: int
    total: int
    auto_linked: int
    per_day: dict[date, int]
    per_court: dict[str, int]

    @property
    def auto_link_rate(self) -> float | None:
        return self.auto_linked / self.total if self.total else None


class PublicationMetricsService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.repository = PublicationRepository(session)
        self.alerts = IntegrationAlertRepository(session)

    async def get_metrics(
        self, *, period_days: int = METRICS_PERIOD_DAYS_DEFAULT, today: date | None = None
    ) -> PublicationMetrics:
        today = today or date.today()
        since = today - timedelta(days=period_days - 1)
        row = await self.repository.metrics(since=since)
        return PublicationMetrics(
            period_days=period_days,
            total=row.total,
            auto_linked=row.auto_linked,
            per_day=row.per_day,
            per_court=row.per_court,
        )

    async def check_auto_link_rate(self, *, now: datetime | None = None) -> IntegrationAlert | None:
        """Regra 8, chamada pelo job diário por tenant. Dedup igual ao alerta
        crítico de saúde da 049: um aberto já basta, não empilha."""
        metrics = await self.get_metrics(period_days=METRICS_PERIOD_DAYS_DEFAULT)
        rate = metrics.auto_link_rate
        if rate is None or rate >= AUTO_LINK_RATE_THRESHOLD:
            return None
        existing = await self.alerts.get_open_by_code(
            integration="djen", code=_LOW_LINK_RATE_CODE, tenant_id=self.tenant_id
        )
        if existing is not None:
            return None
        alert = IntegrationAlert(
            tenant_id=self.tenant_id,
            integration="djen",
            severity="warning",
            code=_LOW_LINK_RATE_CODE,
            message=(
                f"Taxa de vínculo automático nos últimos {metrics.period_days} dias: "
                f"{rate:.0%} (abaixo de {AUTO_LINK_RATE_THRESHOLD:.0%}) — confira se há "
                "processos cadastrados com número de CNJ incorreto."
            ),
        )
        return await self.alerts.create(alert)
