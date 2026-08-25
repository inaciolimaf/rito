"""Regras de negócio do registry de agregados (spec 078): status com defasagem
derivada (regra 6) e o envelope `meta` das respostas de BI (§5)."""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.materialized_view import MATERIALIZED_VIEWS
from app.domain.aggregates.models import AggregateRegistry
from app.domain.aggregates.repository import AggregateRepository
from app.domain.aggregates.schemas import AggregateMeta, AggregateStatusItem

_DESCRIPTIONS = {spec.view_name: spec.description for spec in MATERIALIZED_VIEWS}


def _staleness(
    row: AggregateRegistry, *, now: datetime
) -> tuple[datetime | None, int | None, bool]:
    """Regra 6: `is_stale` quando a defasagem passa de 2× o intervalo configurado.
    View nunca refrescada pelo orquestrador conta como defasada (não há timestamp
    para provar o contrário)."""
    if row.last_refresh_at is None:
        return None, None, True
    last_refresh = row.last_refresh_at
    if last_refresh.tzinfo is None:
        last_refresh = last_refresh.replace(tzinfo=UTC)
    staleness = max(0, int((now - last_refresh).total_seconds()))
    return last_refresh, staleness, staleness > 2 * row.refresh_interval_seconds


def _to_status_item(row: AggregateRegistry, *, now: datetime) -> AggregateStatusItem:
    computed_at, staleness, is_stale = _staleness(row, now=now)
    return AggregateStatusItem(
        name=row.name,
        description=_DESCRIPTIONS.get(row.name, ""),
        refresh_interval_seconds=row.refresh_interval_seconds,
        invalidate_on=list(row.invalidate_on),
        last_refresh_at=row.last_refresh_at,
        last_refresh_duration_ms=row.last_refresh_duration_ms,
        last_error=row.last_error,
        is_enabled=row.is_enabled,
        computed_at=computed_at,
        staleness_seconds=staleness,
        is_stale=is_stale,
    )


class AggregateService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = AggregateRepository(session)

    async def status(self, *, now: datetime) -> list[AggregateStatusItem]:
        rows = await self.repo.list_all()
        return [_to_status_item(row, now=now) for row in rows]

    async def status_item(self, name: str, *, now: datetime) -> AggregateStatusItem | None:
        row = await self.repo.get(name)
        if row is None:
            return None
        return _to_status_item(row, now=now)


async def view_meta(session: AsyncSession, view_name: str, *, now: datetime) -> AggregateMeta:
    """Envelope `meta` de uma resposta de BI atrelada a uma view materializada (§5).
    View fora do registry ou nunca refrescada conta como defasada (regra 6) — o
    metadado nunca derruba a resposta (regra 7: BI velho é melhor que BI ausente)."""
    row = await AggregateRepository(session).get(view_name)
    if row is None:
        return AggregateMeta(computed_at=None, staleness_seconds=None, is_stale=True)
    computed_at, staleness, is_stale = _staleness(row, now=now)
    return AggregateMeta(computed_at=computed_at, staleness_seconds=staleness, is_stale=is_stale)


def realtime_meta(*, now: datetime | None = None) -> AggregateMeta:
    """Envelope `meta` dos endpoints de BI calculados em tempo real (sem view) —
    defasagem zero por construção."""
    moment = now or datetime.now(UTC)
    return AggregateMeta(computed_at=moment, staleness_seconds=0, is_stale=False)
