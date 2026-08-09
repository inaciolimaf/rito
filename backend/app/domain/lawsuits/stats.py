"""Dashboard de processos (spec 028): agregações de topo da listagem e cache curto.

Duas queries apenas (regra de orçamento do plano de testes: ≤ 4 statements): uma de
agregados condicionais (ativos, fechamentos e arquivamentos do mês e do anterior) e uma
de volume por fase. O resultado fica 5 minutos no Redis por (tenant, mês) e é invalidado
ao criar, fechar ou arquivar processo (regra 7).
"""

import json
import uuid
from collections.abc import Awaitable
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Protocol

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.lawsuits.models import Lawsuit
from app.domain.stages.models import Stage, Step
from app.domain.taskscore.models import ClosureGoal

# Regra 7: cache de 5 minutos por tenant e mês.
CACHE_TTL_SECONDS = 300


class StatsCache(Protocol):
    """Contrato mínimo do cache — o Redis do app satisfaz estruturalmente; os testes
    usam um fake em memória sem tocar a rede. Assinaturas espelham o redis-py (nome do
    parâmetro `name`, retorno Awaitable) para o Redis satisfazer o Protocol sem cast."""

    def get(self, name: str) -> Awaitable[bytes | str | None]: ...

    def set(self, name: str, value: str, *, ex: int) -> Awaitable[object]: ...

    def delete(self, *names: str) -> Awaitable[object]: ...


@dataclass
class StatsCard:
    """Um card com comparação. `delta_pct` None = "novo" (regra 2): o período anterior
    estava zerado e dividir por zero viraria ∞."""

    value: int
    delta_pct: float | None
    previous: int


@dataclass
class StepVolume:
    step: str
    count: int
    pct: float


@dataclass
class ClosureGoalWidget:
    """Widget de meta de fechamentos (spec 028) alimentado pela soma das metas por
    grupo de ação configuradas na spec 039 (regra 8 dela)."""

    target: int
    achieved: int
    pct: float


@dataclass
class LawsuitStats:
    active: StatsCard
    closed_this_month: StatsCard
    archived_this_month: StatsCard
    volume_by_step: list[StepVolume]
    # Nenhuma meta configurada (soma dos grupos = 0) → None e o widget convida a
    # configurar (regra 6).
    closure_goal: ClosureGoalWidget | None = None


def cache_key(tenant_id: uuid.UUID, month: date) -> str:
    return f"lawsuits:stats:{tenant_id}:{month:%Y-%m}"


async def invalidate_stats_cache(
    cache: StatsCache, tenant_id: uuid.UUID, *cycle_dates: date | None
) -> None:
    """Regra 7: criar, fechar ou arquivar processo derruba o cache do tenant.

    Toca sempre o mês corrente (ativos e volume por fase refletem o agora) e os meses
    das datas de ciclo envolvidas — fechamento/arquivamento retroativo muda o card
    daquele mês, não o do mês corrente."""
    months = {date.today().replace(day=1)}
    months.update(value.replace(day=1) for value in cycle_dates if value is not None)
    await cache.delete(*(cache_key(tenant_id, month) for month in sorted(months)))


def previous_month(month: date) -> date:
    return (month - timedelta(days=1)).replace(day=1)


def _next_month(month: date) -> date:
    return date(month.year + (month.month == 12), month.month % 12 + 1, 1)


def _delta(current: int, previous: int) -> float | None:
    # Regra 2: anterior zerado → "novo" (None), nunca ∞.
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


class LawsuitStatsRepository:
    """Agregações sobre `lawsuits` — o filtro de tenant é do RLS, nunca de WHERE."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _active_as_of(end_exclusive: object) -> ColumnElement[bool]:
        """Regra 3 (ativos = não arquivados e sem archived_date) reconstruída num ponto
        do tempo: criado antes do corte e sem arquivamento até ele. `is_archived` não
        tem data — a reconstrução histórica usa só `archived_date` (ver §9 da spec)."""
        return and_(
            Lawsuit.created_at < end_exclusive,
            or_(
                Lawsuit.archived_date.is_(None),
                Lawsuit.archived_date >= end_exclusive,
            ),
        )

    async def cycle_counts(self, month: date) -> tuple[int, int, int, int, int, int]:
        """Uma query com os 6 agregados: ativos (agora e no fim do mês anterior),
        fechamentos e arquivamentos do mês de referência e do anterior."""
        prev = previous_month(month)
        following = _next_month(month)
        stmt = select(
            func.count().filter(self._active_as_of(func.now())).label("active_now"),
            func.count().filter(self._active_as_of(month)).label("active_prev_end"),
            func.count()
            .filter(and_(Lawsuit.closure_date >= month, Lawsuit.closure_date < following))
            .label("closed"),
            func.count()
            .filter(and_(Lawsuit.closure_date >= prev, Lawsuit.closure_date < month))
            .label("closed_prev"),
            func.count()
            .filter(and_(Lawsuit.archived_date >= month, Lawsuit.archived_date < following))
            .label("archived"),
            func.count()
            .filter(and_(Lawsuit.archived_date >= prev, Lawsuit.archived_date < month))
            .label("archived_prev"),
        )
        row = (await self.session.execute(stmt)).one()
        return (
            int(row.active_now),
            int(row.active_prev_end),
            int(row.closed),
            int(row.closed_prev),
            int(row.archived),
            int(row.archived_prev),
        )

    async def volume_by_step(self) -> list[tuple[str, int]]:
        """Regra 5: só ativos (não arquivados e sem archived_date)."""
        stmt = (
            select(Step.name, func.count().label("count"))
            .select_from(Lawsuit)
            .join(Stage, Stage.id == Lawsuit.stage_id)
            .join(Step, Step.id == Stage.step_id)
            .where(Lawsuit.is_archived.is_(False), Lawsuit.archived_date.is_(None))
            .group_by(Step.name)
            .order_by(func.count().desc(), Step.name)
        )
        return [(str(name), int(count)) for name, count in (await self.session.execute(stmt))]

    async def closure_target(self) -> int:
        """Soma das metas mensais por grupo de ação (spec 039, regra 8) — RLS filtra
        o tenant, nunca um WHERE manual."""
        value = await self.session.scalar(
            select(func.coalesce(func.sum(ClosureGoal.monthly_target), 0))
        )
        return int(value or 0)


async def get_stats(
    session: AsyncSession, tenant_id: uuid.UUID, month: date, cache: StatsCache
) -> LawsuitStats:
    key = cache_key(tenant_id, month)
    cached = await cache.get(key)
    if cached is not None:
        raw = json.loads(cached)
        raw_goal = raw.get("closure_goal")
        return LawsuitStats(
            active=StatsCard(**raw["active"]),
            closed_this_month=StatsCard(**raw["closed_this_month"]),
            archived_this_month=StatsCard(**raw["archived_this_month"]),
            volume_by_step=[StepVolume(**item) for item in raw["volume_by_step"]],
            closure_goal=ClosureGoalWidget(**raw_goal) if raw_goal else None,
        )

    repository = LawsuitStatsRepository(session)
    active_now, active_prev, closed, closed_prev, archived, archived_prev = (
        await repository.cycle_counts(month)
    )
    volumes = await repository.volume_by_step()
    target = await repository.closure_target()
    total = sum(count for _name, count in volumes)

    stats = LawsuitStats(
        active=StatsCard(
            value=active_now, delta_pct=_delta(active_now, active_prev), previous=active_prev
        ),
        closed_this_month=StatsCard(
            value=closed, delta_pct=_delta(closed, closed_prev), previous=closed_prev
        ),
        archived_this_month=StatsCard(
            value=archived, delta_pct=_delta(archived, archived_prev), previous=archived_prev
        ),
        volume_by_step=[
            StepVolume(step=name, count=count, pct=round(count / total * 100, 1))
            for name, count in volumes
        ],
        closure_goal=(
            ClosureGoalWidget(target=target, achieved=closed, pct=round(closed / target * 100, 1))
            if target > 0
            else None
        ),
    )
    await cache.set(key, json.dumps(asdict(stats)), ex=CACHE_TTL_SECONDS)
    return stats
