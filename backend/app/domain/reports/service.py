import uuid
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dates import month_end
from app.core.materialized_view import MATERIALIZED_VIEWS
from app.domain.reports.repository import ReportsRepository
from app.domain.reports.schemas import (
    AgilityResponse,
    DelayedTaskItem,
    DelayedUserItem,
    MostDelayedResponse,
    ProductivityResponse,
    WeeklyChartPoint,
    WeeklyChartResponse,
)

_AGILITY_VIEW = next(v for v in MATERIALIZED_VIEWS if v.view_name == "agility_daily")

_WEEKDAY_LABELS = ["Seg", "Ter", "Qua", "Qui", "Sex"]


def _current_week_monday(today: date) -> date:
    return today - timedelta(days=today.weekday())


class ReportsService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.repo = ReportsRepository(session)
        self.tenant_id = tenant_id

    async def agility(
        self, *, user_id: uuid.UUID | None, start: date, end: date
    ) -> AgilityResponse:
        totals = await self.repo.agility_totals(user_id=user_id, start=start, end=end)
        avg_days = (
            float(totals.sum_days_to_complete / totals.completed_count)
            if totals.completed_count > 0
            else None
        )
        avg_delay = float(totals.sum_delay_days / totals.late) if totals.late > 0 else None
        return AgilityResponse(
            on_time=totals.on_time,
            late=totals.late,
            pending=totals.pending,
            avg_days_to_complete=round(avg_days, 2) if avg_days is not None else None,
            avg_delay_days=round(avg_delay, 2) if avg_delay is not None else None,
            staleness_hint=_AGILITY_VIEW.staleness_hint(),
        )

    async def most_delayed(self, *, limit: int) -> MostDelayedResponse:
        tasks = await self.repo.most_delayed_tasks(limit=limit)
        users = await self.repo.most_delayed_users(limit=limit)
        return MostDelayedResponse(
            tasks=[
                DelayedTaskItem(
                    post_id=row.post_id,
                    task_type_name=row.task_type_name,
                    user_name=row.user_name,
                    lawsuit_folder=row.lawsuit_folder,
                    deadline_date=row.deadline_date,
                    completed_at_date=row.completed_at_date,
                    delay_days=row.delay_days,
                )
                for row in tasks
            ],
            users=[
                DelayedUserItem(
                    user_id=row.user_id,
                    user_name=row.user_name,
                    late_count=row.late_count,
                    avg_delay_days=round(float(row.sum_delay_days / row.late_count), 2),
                )
                for row in users
            ],
        )

    async def productivity(self, *, user_id: uuid.UUID | None, month: date) -> ProductivityResponse:
        end = month_end(month.year, month.month)
        assigned, completed, late, due_soon = await self.repo.productivity_summary(
            user_id=user_id, month_start=month, month_end=end
        )
        return ProductivityResponse(
            assigned=assigned, completed=completed, late=late, due_in_5_days=due_soon
        )

    async def productivity_weekly(
        self, *, user_id: uuid.UUID | None, today: date
    ) -> WeeklyChartResponse:
        monday = _current_week_monday(today)
        friday = monday + timedelta(days=4)
        assigned_by_day, completed_by_day = await self.repo.weekly_counts(
            user_id=user_id, monday=monday, friday=friday
        )
        days = [
            WeeklyChartPoint(
                label=_WEEKDAY_LABELS[offset],
                day=monday + timedelta(days=offset),
                assigned=assigned_by_day.get(monday + timedelta(days=offset), 0),
                completed=completed_by_day.get(monday + timedelta(days=offset), 0),
            )
            for offset in range(5)
        ]
        return WeeklyChartResponse(days=days)
