"""Agregações de Agilidade e Produtividade (spec 071).

Nenhuma query filtra tenant no WHERE: post_users/posts/users/task_types/lawsuits têm
RLS; a view barreira agility_daily_visible embute o filtro na definição (migration 071).
"""

import uuid
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import Date, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.lawsuits.models import Lawsuit
from app.domain.posts.models import Post, PostUser
from app.domain.reports.models import AgilityTotals, DelayedTaskRow, DelayedUserRow, agility_daily
from app.domain.task_types.models import TaskType
from app.domain.users.models import User

# Regra 7 (spec 033): tarefa privada é invisível a terceiros, mesmo para GESTOR. As
# listas de detalhe (não os agregados) excluem posts privados por segurança — os
# agregados (view de agilidade) já contam tudo sem expor conteúdo.
_MOST_DELAYED_TASKS_LIMIT_CAP = 100


class ReportsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---- agilidade (view barreira) ---------------------------------------------

    async def agility_totals(
        self, *, user_id: uuid.UUID | None, start: date, end: date
    ) -> AgilityTotals:
        conditions = [agility_daily.c.day >= start, agility_daily.c.day <= end]
        if user_id is not None:
            conditions.append(agility_daily.c.user_id == user_id)
        stmt = select(
            func.coalesce(func.sum(agility_daily.c.on_time), 0),
            func.coalesce(func.sum(agility_daily.c.late), 0),
            func.coalesce(func.sum(agility_daily.c.completed_count), 0),
            func.coalesce(func.sum(agility_daily.c.sum_days_to_complete), 0),
            func.coalesce(func.sum(agility_daily.c.sum_delay_days), 0),
        ).where(*conditions)
        on_time, late, completed_count, sum_days, sum_delay = (
            await self.session.execute(stmt)
        ).one()
        pending = await self._pending_count(user_id=user_id, start=start, end=end)
        return AgilityTotals(
            on_time=int(on_time),
            late=int(late),
            pending=pending,
            completed_count=int(completed_count),
            sum_days_to_complete=Decimal(sum_days),
            sum_delay_days=Decimal(sum_delay),
        )

    async def _pending_count(self, *, user_id: uuid.UUID | None, start: date, end: date) -> int:
        """Regra 3: pendente = não concluída, ancorada pelo prazo fatal no período
        (tarefa sem prazo fatal não tem como entrar num relatório por período)."""
        conditions = [
            PostUser.completed_at.is_(None),
            Post.deadline_date.is_not(None),
            Post.deadline_date >= start,
            Post.deadline_date <= end,
        ]
        if user_id is not None:
            conditions.append(PostUser.user_id == user_id)
        stmt = (
            select(func.count())
            .select_from(PostUser)
            .join(Post, Post.id == PostUser.post_id)
            .where(*conditions)
        )
        return int(await self.session.scalar(stmt) or 0)

    # ---- mais atrasados ---------------------------------------------------------

    async def most_delayed_tasks(self, *, limit: int) -> Sequence[DelayedTaskRow]:
        capped_limit = min(limit, _MOST_DELAYED_TASKS_LIMIT_CAP)
        delay = (func.cast(PostUser.completed_at, Date) - Post.deadline_date).label("delay_days")
        stmt = (
            select(
                Post.id,
                TaskType.name,
                User.name,
                Lawsuit.folder,
                Post.deadline_date,
                func.cast(PostUser.completed_at, Date),
                delay,
            )
            .select_from(PostUser)
            .join(Post, Post.id == PostUser.post_id)
            .join(TaskType, TaskType.id == Post.task_type_id)
            .join(User, User.id == PostUser.user_id)
            .join(Lawsuit, Lawsuit.id == Post.lawsuit_id)
            .where(
                Post.is_private.is_(False),
                PostUser.completed_at.is_not(None),
                Post.deadline_date.is_not(None),
                func.cast(PostUser.completed_at, Date) > Post.deadline_date,
            )
            .order_by(delay.desc())
            .limit(capped_limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            DelayedTaskRow(
                post_id=row[0],
                task_type_name=row[1],
                user_name=row[2],
                lawsuit_folder=row[3],
                deadline_date=row[4],
                completed_at_date=row[5],
                delay_days=int(row[6]),
            )
            for row in rows
        ]

    async def most_delayed_users(self, *, limit: int) -> Sequence[DelayedUserRow]:
        total_late = func.sum(agility_daily.c.late)
        total_delay = func.sum(agility_daily.c.sum_delay_days)
        stmt = (
            select(agility_daily.c.user_id, User.name, total_late, total_delay)
            .join(User, User.id == agility_daily.c.user_id)
            .group_by(agility_daily.c.user_id, User.name)
            .having(total_late > 0)
            .order_by(total_late.desc(), total_delay.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            DelayedUserRow(
                user_id=user_id,
                user_name=user_name,
                late_count=int(late_count),
                sum_delay_days=Decimal(sum_delay),
            )
            for user_id, user_name, late_count, sum_delay in rows
        ]

    # ---- produtividade (tempo real, direto em post_users/posts) ----------------

    async def productivity_summary(
        self, *, user_id: uuid.UUID | None, month_start: date, month_end: date
    ) -> tuple[int, int, int, int]:
        """assigned, completed, late, due_in_5_days."""
        assigned = await self._count_assigned(user_id, month_start, month_end)
        completed = await self._count_completed(user_id, month_start, month_end, late_only=False)
        late = await self._count_completed(user_id, month_start, month_end, late_only=True)
        due_soon = await self._count_due_in_5_days(user_id)
        return assigned, completed, late, due_soon

    async def _count_assigned(self, user_id: uuid.UUID | None, start: date, end: date) -> int:
        conditions = [Post.created_at >= start, Post.created_at < end + timedelta(days=1)]
        if user_id is not None:
            conditions.append(PostUser.user_id == user_id)
        stmt = (
            select(func.count())
            .select_from(PostUser)
            .join(Post, Post.id == PostUser.post_id)
            .where(*conditions)
        )
        return int(await self.session.scalar(stmt) or 0)

    async def _count_completed(
        self, user_id: uuid.UUID | None, start: date, end: date, *, late_only: bool
    ) -> int:
        conditions = [
            PostUser.completed_at.is_not(None),
            PostUser.completed_at >= start,
            PostUser.completed_at < end + timedelta(days=1),
        ]
        if user_id is not None:
            conditions.append(PostUser.user_id == user_id)
        stmt = select(func.count()).select_from(PostUser).join(Post, Post.id == PostUser.post_id)
        if late_only:
            conditions += [
                Post.deadline_date.is_not(None),
                func.cast(PostUser.completed_at, Date) > Post.deadline_date,
            ]
        stmt = stmt.where(*conditions)
        return int(await self.session.scalar(stmt) or 0)

    async def _count_due_in_5_days(self, user_id: uuid.UUID | None) -> int:
        today = date.today()
        conditions = [
            PostUser.completed_at.is_(None),
            Post.deadline_date.is_not(None),
            Post.deadline_date >= today,
            Post.deadline_date <= today + timedelta(days=5),
        ]
        if user_id is not None:
            conditions.append(PostUser.user_id == user_id)
        stmt = (
            select(func.count())
            .select_from(PostUser)
            .join(Post, Post.id == PostUser.post_id)
            .where(*conditions)
        )
        return int(await self.session.scalar(stmt) or 0)

    # ---- gráfico semanal ---------------------------------------------------------

    async def weekly_counts(
        self, *, user_id: uuid.UUID | None, monday: date, friday: date
    ) -> tuple[dict[date, int], dict[date, int]]:
        """Atribuídas × concluídas por dia, segunda a sexta (regra 6)."""
        assigned_conditions = [
            Post.created_at >= monday,
            Post.created_at < friday + timedelta(days=1),
        ]
        completed_conditions = [
            PostUser.completed_at.is_not(None),
            PostUser.completed_at >= monday,
            PostUser.completed_at < friday + timedelta(days=1),
        ]
        if user_id is not None:
            assigned_conditions.append(PostUser.user_id == user_id)
            completed_conditions.append(PostUser.user_id == user_id)

        assigned_stmt = (
            select(func.cast(Post.created_at, Date), func.count())
            .select_from(PostUser)
            .join(Post, Post.id == PostUser.post_id)
            .where(*assigned_conditions)
            .group_by(func.cast(Post.created_at, Date))
        )
        completed_stmt = (
            select(func.cast(PostUser.completed_at, Date), func.count())
            .select_from(PostUser)
            .join(Post, Post.id == PostUser.post_id)
            .where(*completed_conditions)
            .group_by(func.cast(PostUser.completed_at, Date))
        )
        assigned_rows = (await self.session.execute(assigned_stmt)).all()
        completed_rows = (await self.session.execute(completed_stmt)).all()
        return (
            {day: int(count) for day, count in assigned_rows},
            {day: int(count) for day, count in completed_rows},
        )
