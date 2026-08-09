import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.posts.models import Post, PostUser
from app.domain.task_types.models import TaskType


@dataclass
class ScheduleRow:
    """Linha plana da agenda — post + tipo + linhas de responsáveis, sem ORM exposto
    para fora do repositório."""

    post_id: uuid.UUID
    lawsuit_id: uuid.UUID
    task_type_name: str
    created_by: uuid.UUID
    scheduled_date: date | None
    scheduled_time: time | None
    end_date: date | None
    end_time: time | None
    deadline_date: date | None
    all_day: bool
    location: str | None
    is_urgent: bool
    is_important: bool
    is_private: bool
    assignees: list[tuple[uuid.UUID, str, bool]] = field(default_factory=list)
    # (user_id, nome, concluiu) — uma entrada por responsável.


class ScheduleRepository:
    """Acesso a dados da agenda (spec 037). Não herda BaseRepository porque a consulta
    é uma composição de posts + task_types + post_users, não CRUD de uma entidade."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_posts(
        self,
        *,
        start: date,
        end: date,
        date_field: str,
        user_id: uuid.UUID | None,
        exclude_ids: set[uuid.UUID] | None = None,
    ) -> Sequence[tuple[Post, str]]:
        """Posts com `show_in_schedule` cujo eixo (compromisso ou prazo fatal — regra 2)
        cai em [start, end]. `user_id` restringe aos posts em que ele é responsável
        (regra 1: filtro por usuário). RLS já garante o tenant."""
        axis = Post.scheduled_date if date_field == "scheduled" else Post.deadline_date
        stmt = (
            select(Post, TaskType.name)
            .join(TaskType, TaskType.id == Post.task_type_id)
            .where(Post.show_in_schedule.is_(True))
            .where(axis.is_not(None))
            .where(axis.between(start, end))
            .order_by(axis, Post.scheduled_time.nulls_first(), Post.id)
        )
        if user_id is not None:
            stmt = stmt.join(PostUser, PostUser.post_id == Post.id).where(
                PostUser.user_id == user_id
            )
        if exclude_ids:
            stmt = stmt.where(Post.id.notin_(exclude_ids))
        result = await self.session.execute(stmt)
        return [(post, name) for post, name in result.all()]

    async def assignee_lines(
        self, post_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[tuple[uuid.UUID, str, bool]]]:
        """Responsáveis + flag de conclusão de vários posts em UMA query (sem N+1)."""
        if not post_ids:
            return {}
        from app.domain.users.models import User

        stmt = (
            select(PostUser.post_id, User.id, User.name, PostUser.completed_at)
            .join(User, User.id == PostUser.user_id)
            .where(PostUser.post_id.in_(post_ids))
            .order_by(User.name)
        )
        result: dict[uuid.UUID, list[tuple[uuid.UUID, str, bool]]] = {
            post_id: [] for post_id in post_ids
        }
        for post_id, user_id, name, completed_at in await self.session.execute(stmt):
            result[post_id].append((user_id, name, completed_at is not None))
        return result
