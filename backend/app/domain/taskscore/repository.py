import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import Date, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.action_groups.models import ActionGroup
from app.domain.posts.models import Post, PostUser
from app.domain.taskscore.models import ClosureGoal, MonthlyScore, user_monthly_scores
from app.domain.users.models import User


def next_month(month: date) -> date:
    return date(month.year + (month.month == 12), month.month % 12 + 1, 1)


class TaskscoreRepository:
    """Agregações do Taskscore. Nenhuma query filtra tenant no WHERE: post_users/posts/
    users/action_groups/closure_goals têm RLS; a view barreira user_monthly_scores_visible
    embute o filtro na definição (migration 039)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---- metas de fechamento -------------------------------------------------

    async def list_closure_goals(self) -> Sequence[tuple[ActionGroup, int | None]]:
        """Todos os grupos ativos com a meta (None = grupo sem meta configurada)."""
        stmt = (
            select(ActionGroup, ClosureGoal.monthly_target)
            .outerjoin(ClosureGoal, ClosureGoal.action_group_id == ActionGroup.id)
            .where(ActionGroup.is_active.is_(True))
            .order_by(ActionGroup.name)
        )
        rows = (await self.session.execute(stmt)).all()
        return [(group, target) for group, target in rows]

    async def upsert_closure_goal(
        self, tenant_id: uuid.UUID, action_group_id: uuid.UUID, monthly_target: int
    ) -> None:
        existing = await self.session.scalar(
            select(ClosureGoal).where(ClosureGoal.action_group_id == action_group_id)
        )
        if existing is None:
            self.session.add(
                ClosureGoal(
                    tenant_id=tenant_id,
                    action_group_id=action_group_id,
                    monthly_target=monthly_target,
                )
            )
        else:
            existing.monthly_target = monthly_target

    async def existing_group_ids(self, ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
        if not ids:
            return set()
        stmt = select(ActionGroup.id).where(ActionGroup.id.in_(ids))
        return set((await self.session.scalars(stmt)).all())

    async def sum_closure_targets(self) -> int:
        """Soma das metas de todos os grupos — alimenta o widget da spec 028 (regra 8)."""
        value = await self.session.scalar(
            select(func.coalesce(func.sum(ClosureGoal.monthly_target), 0))
        )
        return int(value or 0)

    # ---- pontuação (view barreira) -------------------------------------------

    async def monthly_score(self, user_id: uuid.UUID, month: date) -> MonthlyScore | None:
        stmt = select(user_monthly_scores).where(
            user_monthly_scores.c.user_id == user_id,
            user_monthly_scores.c.month == month,
        )
        row = (await self.session.execute(stmt)).mappings().one_or_none()
        if row is None:
            return None
        return MonthlyScore(
            user_id=user_id,
            month=month,
            tasks_completed=int(row["tasks_completed"]),
            points=int(row["points"]),
            on_time=int(row["on_time"]),
            late=int(row["late"]),
        )

    async def scores_by_user(self, month: date | None) -> dict[uuid.UUID, MonthlyScore]:
        """Soma por usuário: do mês informado ou de todos os meses (ELTV, regra 5)."""
        stmt = select(
            user_monthly_scores.c.user_id,
            func.coalesce(func.sum(user_monthly_scores.c.points), 0).label("points"),
            func.coalesce(func.sum(user_monthly_scores.c.tasks_completed), 0).label(
                "tasks_completed"
            ),
            func.coalesce(func.sum(user_monthly_scores.c.on_time), 0).label("on_time"),
            func.coalesce(func.sum(user_monthly_scores.c.late), 0).label("late"),
        ).group_by(user_monthly_scores.c.user_id)
        if month is not None:
            stmt = stmt.where(user_monthly_scores.c.month == month)
        result: dict[uuid.UUID, MonthlyScore] = {}
        for row in (await self.session.execute(stmt)).mappings():
            user_id = row["user_id"]
            result[user_id] = MonthlyScore(
                user_id=user_id,
                month=month or date.min,
                tasks_completed=int(row["tasks_completed"]),
                points=int(row["points"]),
                on_time=int(row["on_time"]),
                late=int(row["late"]),
            )
        return result

    async def daily_points(self, user_id: uuid.UUID, month: date) -> Sequence[tuple[date, int]]:
        """Pontos por dia do mês — visão diária do gráfico (a view agrega por mês,
        então aqui a soma é direta em post_users, que tem RLS)."""
        stmt = (
            select(
                func.cast(PostUser.completed_at, Date).label("day"),
                func.coalesce(func.sum(PostUser.points_earned), 0).label("points"),
            )
            .where(
                PostUser.user_id == user_id,
                PostUser.completed_at.is_not(None),
                PostUser.completed_at >= month,
                PostUser.completed_at < next_month(month),
            )
            .group_by("day")
            .order_by("day")
        )
        return [(row.day, int(row.points)) for row in (await self.session.execute(stmt)).mappings()]

    # ---- envolvimento (regra 4: concluídas ÷ atribuídas no período) -----------

    async def assigned_by_user(self, month: date | None) -> dict[uuid.UUID, int]:
        """Atribuídas = responsabilidades criadas no período (posts.created_at — a
        atribuição acontece na criação do post; ELTV = todas)."""
        stmt = select(PostUser.user_id, func.count().label("assigned")).group_by(PostUser.user_id)
        if month is not None:
            stmt = stmt.join(Post, Post.id == PostUser.post_id).where(
                Post.created_at >= month, Post.created_at < next_month(month)
            )
        return {
            row.user_id: int(row.assigned) for row in (await self.session.execute(stmt)).mappings()
        }

    async def count_assigned(self, user_id: uuid.UUID, month: date | None) -> int:
        return (await self.assigned_by_user(month)).get(user_id, 0)

    # ---- usuários do ranking ---------------------------------------------------

    async def ranking_users(self, *, include_inactive: bool) -> Sequence[User]:
        """Regra 10: o mês corrente esconde inativos; o histórico os mantém."""
        stmt = select(User).order_by(User.name, User.id)
        if not include_inactive:
            stmt = stmt.where(User.is_active.is_(True))
        return (await self.session.scalars(stmt)).all()

    async def delete_closure_goal(self, action_group_id: uuid.UUID) -> None:
        await self.session.execute(
            delete(ClosureGoal).where(ClosureGoal.action_group_id == action_group_id)
        )
