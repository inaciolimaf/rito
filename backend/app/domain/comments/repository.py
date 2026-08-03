import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, literal, select, tuple_

from app.core.repository import BaseRepository
from app.domain.comments.models import PostComment


class CommentRepository(BaseRepository[PostComment]):
    model = PostComment

    async def create(self, comment: PostComment) -> PostComment:
        self.session.add(comment)
        await self.session.flush()
        return comment

    async def list_for_post(
        self,
        post_id: uuid.UUID,
        *,
        cursor: tuple[datetime, uuid.UUID] | None,
        limit: int,
    ) -> Sequence[PostComment]:
        """Regra 10: thread por criação crescente, keyset em (created_at, id) —
        inclui os soft-deleted (regra 4: a thread se preserva; a máscara é da UI)."""
        stmt = (
            select(PostComment)
            .where(PostComment.post_id == post_id)
            .order_by(PostComment.created_at, PostComment.id)
            .limit(limit + 1)
        )
        if cursor is not None:
            cursor_value, cursor_id = cursor
            stmt = stmt.where(
                tuple_(PostComment.created_at, PostComment.id)
                > tuple_(literal(cursor_value), literal(cursor_id))
            )
        return (await self.session.scalars(stmt)).all()

    async def count_for_post(self, post_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(PostComment).where(PostComment.post_id == post_id)
        return int((await self.session.execute(stmt)).scalar_one())
