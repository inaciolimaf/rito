import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select, update

from app.core.repository import BaseRepository
from app.domain.posts.models import Post, PostUser
from app.domain.users.models import User


class PostRepository(BaseRepository[Post]):
    model = Post

    async def create_with_assignees(self, post: Post, user_ids: Sequence[uuid.UUID]) -> Post:
        self.session.add(post)
        await self.session.flush()
        for user_id in dict.fromkeys(user_ids):  # dedupe preservando a ordem
            self.session.add(PostUser(tenant_id=post.tenant_id, post_id=post.id, user_id=user_id))
        await self.session.flush()
        return post

    async def replace_assignees(self, post: Post, user_ids: Sequence[uuid.UUID]) -> None:
        await self.session.execute(sql_delete(PostUser).where(PostUser.post_id == post.id))
        for user_id in dict.fromkeys(user_ids):
            self.session.add(PostUser(tenant_id=post.tenant_id, post_id=post.id, user_id=user_id))
        await self.session.flush()

    async def list_for_lawsuit(self, lawsuit_id: uuid.UUID) -> Sequence[Post]:
        stmt = (
            select(Post)
            .where(Post.lawsuit_id == lawsuit_id)
            .order_by(Post.scheduled_date.desc().nulls_last(), Post.created_at.desc())
        )
        return (await self.session.scalars(stmt)).all()

    async def assignees_for(self, post_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[User]]:
        """Responsáveis de vários posts em UMA query (sem N+1), na ordem alfabética."""
        if not post_ids:
            return {}
        stmt = (
            select(PostUser.post_id, User)
            .join(User, User.id == PostUser.user_id)
            .where(PostUser.post_id.in_(post_ids))
            .order_by(User.name)
        )
        result: dict[uuid.UUID, list[User]] = {post_id: [] for post_id in post_ids}
        for post_id, user in await self.session.execute(stmt):
            result[post_id].append(user)
        return result

    async def assignee_ids_for(self, post_id: uuid.UUID) -> set[uuid.UUID]:
        stmt = select(PostUser.user_id).where(PostUser.post_id == post_id)
        return set((await self.session.scalars(stmt)).all())

    async def find_duplicates(
        self, *, lawsuit_id: uuid.UUID, task_type_id: uuid.UUID, scheduled_date: date | None
    ) -> Sequence[Post]:
        """Candidatos à duplicata da regra 4 — a comparação do CONJUNTO de
        responsáveis fica no service (volume por processo é baixo)."""
        stmt = select(Post).where(
            Post.lawsuit_id == lawsuit_id,
            Post.task_type_id == task_type_id,
        )
        if scheduled_date is None:
            stmt = stmt.where(Post.scheduled_date.is_(None))
        else:
            stmt = stmt.where(Post.scheduled_date == scheduled_date)
        return (await self.session.scalars(stmt)).all()

    async def count_for_task_type(self, task_type_id: uuid.UUID) -> int:
        """Uso de um tipo de tarefa (regra 5 da spec 031 — plugada aqui)."""
        stmt = select(func.count()).select_from(Post).where(Post.task_type_id == task_type_id)
        return int((await self.session.execute(stmt)).scalar_one())

    async def reassign_task_type(self, *, from_id: uuid.UUID, to_id: uuid.UUID) -> int:
        result = await self.session.execute(
            update(Post)
            .where(Post.task_type_id == from_id)
            .values(task_type_id=to_id)
            .execution_options(synchronize_session=False)
        )
        return int(result.rowcount)  # type: ignore[attr-defined]
