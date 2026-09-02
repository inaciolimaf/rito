import uuid
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from sqlalchemy import ColumnElement, Row, func, select

from app.core.repository import BaseRepository
from app.domain.ai.models import AiCheckpoint, AiFeatureConfig, AiStep, AiThread, AiUsage


def _usage_filters(
    from_: date | None, to: date | None, feature_key: str | None
) -> list[ColumnElement[bool]]:
    """Os mesmos filtros para os grupos e para os totais — é o que faz as duas somas baterem.

    O `to` vai até `datetime.max.time()` do dia, não à meia-noite dele: `<= 2026-09-02` com
    hora zero deixaria de fora o dia inteiro que o usuário pediu.
    """
    filtros: list[ColumnElement[bool]] = []
    if from_ is not None:
        filtros.append(AiUsage.created_at >= datetime.combine(from_, datetime.min.time()))
    if to is not None:
        filtros.append(AiUsage.created_at <= datetime.combine(to, datetime.max.time()))
    if feature_key is not None:
        filtros.append(AiUsage.feature_key == feature_key)
    return filtros


# As mesmas colunas nos dois SELECTs. Uma lista só, porque um agregado que existisse em um
# e não no outro daria um total que não fecha com a soma dos grupos na tela.
_USAGE_AGGREGATES = (
    func.count().label("calls"),
    func.coalesce(func.sum(AiUsage.prompt_tokens), 0).label("prompt_tokens"),
    func.coalesce(func.sum(AiUsage.completion_tokens), 0).label("completion_tokens"),
    func.coalesce(func.sum(AiUsage.cost_usd), 0).label("cost_usd"),
    func.count().filter(AiUsage.status == "error").label("errors"),
)


class AiFeatureConfigRepository(BaseRepository[AiFeatureConfig]):
    model = AiFeatureConfig

    async def get_by_feature(self, feature_key: str) -> AiFeatureConfig | None:
        stmt = select(AiFeatureConfig).where(AiFeatureConfig.feature_key == feature_key)
        return (await self.session.scalars(stmt)).first()

    async def list_all(self) -> Sequence[AiFeatureConfig]:
        stmt = select(AiFeatureConfig).order_by(AiFeatureConfig.feature_key)
        return (await self.session.scalars(stmt)).all()

    async def upsert(self, config: AiFeatureConfig) -> AiFeatureConfig:
        self.session.add(config)
        await self.session.flush()
        return config


class AiUsageRepository(BaseRepository[AiUsage]):
    model = AiUsage

    async def record(self, usage: AiUsage) -> AiUsage:
        self.session.add(usage)
        await self.session.flush()
        return usage

    async def summary(
        self,
        *,
        from_: date | None,
        to: date | None,
        feature_key: str | None,
        group_by: str,
    ) -> tuple[Sequence[Row[Any]], Row[Any]]:
        """Uma query para os grupos e uma para os totais — nunca uma por card
        (CLAUDE.md §6 e checklist da 080)."""
        dimension = {
            "feature": AiUsage.feature_key,
            "model": AiUsage.model,
            "status": AiUsage.status,
        }[group_by]

        filters = _usage_filters(from_, to, feature_key)
        grouped = (
            select(dimension.label("key"), *_USAGE_AGGREGATES)
            .where(*filters)
            .group_by(dimension)
            .order_by(func.count().desc())
        )
        totals = select(
            *_USAGE_AGGREGATES, func.avg(AiUsage.latency_ms).label("avg_latency_ms")
        ).where(*filters)

        rows = (await self.session.execute(grouped)).all()
        total = (await self.session.execute(totals)).one()
        return rows, total

    async def last_for_feature(self, feature_key: str) -> AiUsage | None:
        stmt = (
            select(AiUsage)
            .where(AiUsage.feature_key == feature_key)
            .order_by(AiUsage.created_at.desc())
            .limit(1)
        )
        return (await self.session.scalars(stmt)).first()

    async def count_for_user(self, user_id: uuid.UUID) -> int:
        stmt = select(func.count()).where(AiUsage.user_id == user_id)
        return int(await self.session.scalar(stmt) or 0)


class AiThreadRepository(BaseRepository[AiThread]):
    model = AiThread

    async def create(self, thread: AiThread) -> AiThread:
        self.session.add(thread)
        await self.session.flush()
        return thread

    async def list_for_user(
        self,
        *,
        user_id: uuid.UUID | None,
        cursor: uuid.UUID | None,
        limit: int,
    ) -> tuple[Sequence[AiThread], int]:
        """Regra 11: o thread é do usuário. ADMINISTRADOR em auditoria chama com
        `user_id=None` e enxerga o tenant inteiro."""
        stmt = select(AiThread).order_by(AiThread.updated_at.desc(), AiThread.id)
        if user_id is not None:
            stmt = stmt.where(AiThread.user_id == user_id)
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        if cursor is not None:
            stmt = stmt.where(AiThread.id > cursor)
        rows = (await self.session.scalars(stmt.limit(limit))).all()
        return rows, int(total or 0)

    async def list_waiting_since(self, cutoff: datetime) -> Sequence[AiThread]:
        stmt = select(AiThread).where(
            AiThread.status == "waiting_human", AiThread.waiting_since < cutoff
        )
        return (await self.session.scalars(stmt)).all()


class AiStepRepository(BaseRepository[AiStep]):
    model = AiStep

    async def list_for_thread(self, thread_id: uuid.UUID) -> Sequence[AiStep]:
        stmt = select(AiStep).where(AiStep.thread_id == thread_id).order_by(AiStep.step)
        return (await self.session.scalars(stmt)).all()


class AiCheckpointRepository(BaseRepository[AiCheckpoint]):
    model = AiCheckpoint

    async def last_for_thread(self, thread_id: uuid.UUID) -> AiCheckpoint | None:
        stmt = (
            select(AiCheckpoint)
            .where(AiCheckpoint.thread_id == thread_id)
            .order_by(AiCheckpoint.step.desc())
            .limit(1)
        )
        return (await self.session.scalars(stmt)).first()

    async def count_for_thread(self, thread_id: uuid.UUID) -> int:
        stmt = select(func.count()).where(AiCheckpoint.thread_id == thread_id)
        return int(await self.session.scalar(stmt) or 0)
