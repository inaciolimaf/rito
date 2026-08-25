import uuid
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from sqlalchemy import Row, func, select

from app.core.repository import BaseRepository
from app.domain.ai.models import AiFeatureConfig, AiUsage


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

        filters = []
        if from_ is not None:
            filters.append(AiUsage.created_at >= datetime.combine(from_, datetime.min.time()))
        if to is not None:
            filters.append(AiUsage.created_at <= datetime.combine(to, datetime.max.time()))
        if feature_key is not None:
            filters.append(AiUsage.feature_key == feature_key)

        grouped = (
            select(
                dimension.label("key"),
                func.count().label("calls"),
                func.coalesce(func.sum(AiUsage.prompt_tokens), 0).label("prompt_tokens"),
                func.coalesce(func.sum(AiUsage.completion_tokens), 0).label("completion_tokens"),
                func.coalesce(func.sum(AiUsage.cost_usd), 0).label("cost_usd"),
                func.count().filter(AiUsage.status == "error").label("errors"),
            )
            .where(*filters)
            .group_by(dimension)
            .order_by(func.count().desc())
        )
        totals = select(
            func.count().label("calls"),
            func.coalesce(func.sum(AiUsage.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(AiUsage.completion_tokens), 0).label("completion_tokens"),
            func.coalesce(func.sum(AiUsage.cost_usd), 0).label("cost_usd"),
            func.count().filter(AiUsage.status == "error").label("errors"),
            func.avg(AiUsage.latency_ms).label("avg_latency_ms"),
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
