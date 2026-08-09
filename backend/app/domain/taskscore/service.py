import uuid
from datetime import date
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.taskscore.exceptions import ActionGroupNotFoundError
from app.domain.taskscore.models import MonthlyScore
from app.domain.taskscore.repository import TaskscoreRepository
from app.domain.taskscore.schemas import (
    ChartPoint,
    ClosureGoalItem,
    ClosureGoalResponse,
    ScoreSummary,
)
from app.domain.users.models import User

RankingSort = Literal["points", "volume", "late", "engagement"]


def _summary(user: User, score: MonthlyScore | None, assigned: int) -> ScoreSummary:
    """Regras 3 e 4: sem meta → goal_pct None (a UI mostra "—"); sem atribuídas →
    engagement None (0/0 não é 100% nem 0%)."""
    resolved = score or MonthlyScore(
        user_id=user.id, month=date.min, tasks_completed=0, points=0, on_time=0, late=0
    )
    engagement = round(resolved.tasks_completed / assigned, 3) if assigned > 0 else None
    goal_pct = round(resolved.points / user.points_goal * 100, 1) if user.points_goal else None
    return ScoreSummary(
        user_id=user.id,
        user_name=user.name,
        points=resolved.points,
        tasks_completed=resolved.tasks_completed,
        on_time=resolved.on_time,
        late=resolved.late,
        assigned=assigned,
        engagement=engagement,
        points_goal=user.points_goal,
        goal_pct=goal_pct,
    )


def sort_ranking(items: list[ScoreSummary], sort: RankingSort) -> list[ScoreSummary]:
    """Os 4 critérios da regra 4, sempre com desempate determinístico (nome, id) —
    aceite da spec: ranking determinístico com seed."""
    if sort == "points":
        items.sort(key=lambda item: (-item.points, item.user_name, item.user_id))
    elif sort == "volume":
        items.sort(key=lambda item: (-item.tasks_completed, item.user_name, item.user_id))
    elif sort == "late":
        items.sort(key=lambda item: (-item.late, item.user_name, item.user_id))
    else:
        # Envolvimento: None (nada atribuído) por último, não misturado com 0%.
        items.sort(
            key=lambda item: (
                item.engagement is None,
                -(item.engagement or 0),
                item.user_name,
                item.user_id,
            )
        )
    return items


class TaskscoreService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.repo = TaskscoreRepository(session)
        self.tenant_id = tenant_id

    # ---- metas -----------------------------------------------------------------

    async def list_closure_goals(self) -> list[ClosureGoalResponse]:
        rows = await self.repo.list_closure_goals()
        return [
            ClosureGoalResponse(
                action_group_id=group.id,
                action_group_name=group.name,
                monthly_target=target if target is not None else 0,
            )
            for group, target in rows
        ]

    async def put_closure_goals(self, items: list[ClosureGoalItem]) -> None:
        """Upsert em lote; grupos fora do payload ficam intactos."""
        existing = await self.repo.existing_group_ids([item.action_group_id for item in items])
        if any(item.action_group_id not in existing for item in items):
            raise ActionGroupNotFoundError
        for item in items:
            await self.repo.upsert_closure_goal(
                self.tenant_id, item.action_group_id, item.monthly_target
            )

    async def set_points_goal(self, user: User, points_goal: int | None) -> None:
        user.points_goal = points_goal

    # ---- desempenho --------------------------------------------------------------

    async def my_summary(self, user: User, month: date | None) -> ScoreSummary:
        if month is None:  # ELTV (regra 5)
            score = (await self.repo.scores_by_user(None)).get(user.id)
        else:
            score = await self.repo.monthly_score(user.id, month)
        assigned = await self.repo.count_assigned(user.id, month)
        return _summary(user, score, assigned)

    async def ranking(
        self, sort: RankingSort, month: date | None, *, today: date
    ) -> list[ScoreSummary]:
        # Regra 10: inativo some do ranking do mês corrente, permanece no histórico
        # (mês passado ou ELTV).
        current_month = today.replace(day=1)
        include_inactive = month is None or month != current_month
        users = await self.repo.ranking_users(include_inactive=include_inactive)
        scores = await self.repo.scores_by_user(month)
        assigned = await self.repo.assigned_by_user(month)
        items = [_summary(user, scores.get(user.id), assigned.get(user.id, 0)) for user in users]
        return sort_ranking(items, sort)

    async def chart(
        self, user: User, granularity: Literal["monthly", "daily"], *, today: date
    ) -> tuple[int, int, int | None, list[ChartPoint]]:
        """Gráfico da regra/ADVBOX 4.1: mensal = mês atual × mês anterior × meta;
        diário = pontos por dia do mês corrente."""
        month = today.replace(day=1)
        current = await self.repo.monthly_score(user.id, month)
        days: list[ChartPoint] = []
        if granularity == "daily":
            days = [
                ChartPoint(label=f"{day:%d/%m}", value=points)
                for day, points in await self.repo.daily_points(user.id, month)
            ]
        previous_month_date = (month.replace(day=1) - date.resolution).replace(day=1)
        previous = await self.repo.monthly_score(user.id, previous_month_date)
        return (
            current.points if current else 0,
            previous.points if previous else 0,
            user.points_goal,
            days,
        )
