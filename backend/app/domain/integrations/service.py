"""Saúde e status agregado das integrações externas (spec 049).

`IntegrationHealthService.run_check` é chamado pelo job diário (regra 5, um
`IntegrationHealthChecker` por integração — DJEN/DataJud são implementações,
OCP igual a `PublicationSource` da 044) e grava a telemetria; duas falhas
seguidas da MESMA integração levantam um alerta crítico, deduplicado (regra 6).

`IntegrationStatusService.get_status` monta o painel somente-leitura (§5): por
integração (saudável, última execução com sucesso, latência média, falhas em
24h) e termos monitorados por status — nenhuma escrita aqui.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.integration_alerts.models import IntegrationAlert
from app.domain.integration_alerts.repository import IntegrationAlertRepository
from app.domain.integrations.models import IntegrationHealth
from app.domain.integrations.repository import IntegrationHealthRepository
from app.domain.monitored_terms.models import TermStatus
from app.domain.monitored_terms.repository import MonitoredTermRepository

KNOWN_INTEGRATIONS = ("djen", "datajud")
CONSECUTIVE_UNHEALTHY_ALERT_THRESHOLD = 2  # regra 6
STATUS_WINDOW_HOURS = 24
_HEALTH_CHECK_FAILED_CODE = "health_check_failed"
_DETAIL_MAX = 500


@dataclass
class HealthCheckResult:
    is_healthy: bool
    latency_ms: int | None
    detail: str | None


class IntegrationHealthChecker(Protocol):
    """Uma chamada leve por integração (regra 5). Implementações reais moram em
    `app/integrations/<nome>/health.py`; o teste usa um fake — nenhuma rede aqui."""

    integration: str

    async def check(self) -> HealthCheckResult: ...


class IntegrationHealthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.health = IntegrationHealthRepository(session)
        self.alerts = IntegrationAlertRepository(session)

    async def run_check(self, checker: IntegrationHealthChecker) -> IntegrationHealth:
        try:
            result = await checker.check()
        except Exception as exc:  # a checagem em si nunca deve derrubar o job diário
            result = HealthCheckResult(
                is_healthy=False, latency_ms=None, detail=str(exc)[:_DETAIL_MAX]
            )
        record = await self.health.create(
            IntegrationHealth(
                integration=checker.integration,
                is_healthy=result.is_healthy,
                latency_ms=result.latency_ms,
                detail=result.detail,
            )
        )
        if not result.is_healthy:
            await self._maybe_raise_critical_alert(checker.integration)
        return record

    async def _maybe_raise_critical_alert(self, integration: str) -> None:
        """Regra 6: duas seguidas (as `limit` mais recentes, não uma janela de tempo)
        viram alerta crítico — deduplicado como o alerta de saúde do DataJud (046)."""
        recent = await self.health.list_recent(
            integration, limit=CONSECUTIVE_UNHEALTHY_ALERT_THRESHOLD
        )
        if len(recent) < CONSECUTIVE_UNHEALTHY_ALERT_THRESHOLD or any(r.is_healthy for r in recent):
            return
        existing = await self.alerts.get_open_by_code(
            integration=integration, code=_HEALTH_CHECK_FAILED_CODE
        )
        if existing is not None:
            return
        await self.alerts.create(
            IntegrationAlert(
                tenant_id=None,  # config/infra global, não é problema de um tenant
                integration=integration,
                severity="critical",
                code=_HEALTH_CHECK_FAILED_CODE,
                message=(
                    f"{integration}: {CONSECUTIVE_UNHEALTHY_ALERT_THRESHOLD} verificações de "
                    "saúde seguidas falharam."
                ),
            )
        )


@dataclass
class IntegrationStatusItem:
    integration: str
    is_healthy: bool | None
    last_success_at: datetime | None
    avg_latency_ms: float | None
    failures_24h: int


@dataclass
class TermsByStatusItem:
    status: TermStatus
    count: int


@dataclass
class IntegrationStatus:
    integrations: list[IntegrationStatusItem]
    terms_by_status: list[TermsByStatusItem]


class IntegrationStatusService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.health = IntegrationHealthRepository(session)
        self.terms = MonitoredTermRepository(session)

    async def get_status(self, *, now: datetime | None = None) -> IntegrationStatus:
        now = now or datetime.now(UTC)
        since = now - timedelta(hours=STATUS_WINDOW_HOURS)
        integrations = [await self._status_for(name, since) for name in KNOWN_INTEGRATIONS]
        counts = await self.terms.count_by_status()
        terms_by_status = [
            TermsByStatusItem(status=status, count=count) for status, count in counts.items()
        ]
        return IntegrationStatus(integrations=integrations, terms_by_status=terms_by_status)

    async def _status_for(self, integration: str, since: datetime) -> IntegrationStatusItem:
        recent = await self.health.list_since(integration, since=since)
        if not recent:
            return IntegrationStatusItem(
                integration=integration,
                is_healthy=None,
                last_success_at=None,
                avg_latency_ms=None,
                failures_24h=0,
            )
        latest = recent[0]  # list_since ordena checked_at desc
        return IntegrationStatusItem(
            integration=integration,
            is_healthy=latest.is_healthy,
            last_success_at=_latest_success(recent),
            avg_latency_ms=_avg_latency(recent),
            failures_24h=sum(1 for row in recent if not row.is_healthy),
        )


def _latest_success(rows: Sequence[IntegrationHealth]) -> datetime | None:
    successes = [row.checked_at for row in rows if row.is_healthy]
    return max(successes) if successes else None


def _avg_latency(rows: Sequence[IntegrationHealth]) -> float | None:
    latencies = [row.latency_ms for row in rows if row.latency_ms is not None]
    return sum(latencies) / len(latencies) if latencies else None
