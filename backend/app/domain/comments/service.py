import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.invariants import not_none
from app.domain.attachments.models import Attachment
from app.domain.attachments.service import AttachmentService
from app.domain.comments.mentions import MentionCandidate, resolve_mentions
from app.domain.comments.models import PostComment
from app.domain.comments.repository import CommentRepository
from app.domain.notifications.service import NotificationService
from app.domain.posts.models import Post
from app.domain.posts.repository import PostRepository
from app.domain.posts.visibility import is_involved
from app.domain.users.models import User, UserRole
from app.domain.users.repository import UserRepository
from app.integrations.storage.base import FileStorage

# Regra 3: o autor edita o próprio comentário em até 15 min; depois só ADMINISTRADOR+.
_EDIT_WINDOW = timedelta(minutes=15)
_ADMIN_OR_ABOVE = {UserRole.ADMINISTRADOR, UserRole.GESTOR}

# Trecho do comentário que vai no corpo da notificação de menção.
_NOTIFICATION_EXCERPT_LENGTH = 140


class PostNotFoundError(Exception):
    """Post inexistente ou invisível para o usuário (tarefa privada — 404)."""


class CommentNotFoundError(Exception):
    pass


class CommentEditForbiddenError(Exception):
    """Regra 3: fora da janela de 15 min, só ADMINISTRADOR+ edita/exclui."""


@dataclass
class CommentDetail:
    comment: PostComment
    author_name: str
    attachments: list[Attachment]


class CommentService:
    def __init__(self, session: AsyncSession, storage: FileStorage, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.comments = CommentRepository(session)
        self.posts = PostRepository(session)
        self.users = UserRepository(session)
        self.notifications = NotificationService(session, tenant_id)
        self.attachments = AttachmentService(session, storage, tenant_id)

    async def _accessible_post(self, post_id: uuid.UUID, viewer_id: uuid.UUID) -> Post:
        """Comentar/anexar exige o mesmo acesso de VER a tarefa: privada, só os
        envolvidos (regra 8 da 033 — 404, não 403)."""
        post = await self.posts.get_by_id(post_id)
        if post is None:
            raise PostNotFoundError
        if post.is_private and not is_involved(
            post, await self.posts.assignee_ids_for(post.id), viewer_id
        ):
            raise PostNotFoundError
        return post

    async def _resolve_allowed_mentions(self, post: Post, body: str) -> list[uuid.UUID]:
        candidates = [
            MentionCandidate(user_id=user.id, name=user.name)
            for user in await self.users.list_active_basic()
        ]
        mentioned = resolve_mentions(body, candidates)
        if post.is_private:
            # Regra 2: menção a quem não tem acesso à tarefa é ignorada em silêncio
            # — não notifica e nem fica registrada em mentioned_user_ids.
            involved = {post.created_by} | await self.posts.assignee_ids_for(post.id)
            mentioned = [user_id for user_id in mentioned if user_id in involved]
        return mentioned

    async def _notify_mentions(
        self, post: Post, comment: PostComment, author: User, mentioned: list[uuid.UUID]
    ) -> None:
        excerpt = comment.body[:_NOTIFICATION_EXCERPT_LENGTH]
        for user_id in mentioned:
            if user_id == author.id:
                continue  # mencionar a si mesmo não notifica
            # Regra 8: notificação de menção é in-app; o roteamento por canal é da 069.
            await self.notifications.notify(
                user_id=user_id,
                kind="mention",
                title=f"{author.name} mencionou você em uma tarefa",
                body=excerpt,
                link=f"/posts/{post.id}",
            )

    async def create(self, post_id: uuid.UUID, author: User, body: str) -> CommentDetail:
        post = await self._accessible_post(post_id, author.id)
        mentioned = await self._resolve_allowed_mentions(post, body)
        comment = await self.comments.create(
            PostComment(
                tenant_id=self.tenant_id,
                post_id=post.id,
                author_id=author.id,
                body=body,
                mentioned_user_ids=mentioned,
            )
        )
        # Regra 1: a menção é resolvida na gravação e persistida como ids…
        await self._notify_mentions(post, comment, author, mentioned)
        return await self._detail(comment)

    async def list_for_post(
        self,
        post_id: uuid.UUID,
        viewer_id: uuid.UUID,
        *,
        cursor: tuple[datetime, uuid.UUID] | None,
        limit: int,
    ) -> tuple[list[CommentDetail], int, bool]:
        await self._accessible_post(post_id, viewer_id)
        rows = list(await self.comments.list_for_post(post_id, cursor=cursor, limit=limit))
        total = await self.comments.count_for_post(post_id)
        has_more = len(rows) > limit
        page = rows[:limit]
        attachments_by_comment = await self._attachments_by_comment([row.id for row in page])
        names = await self.users.names_for({row.author_id for row in page})
        return (
            [
                CommentDetail(
                    comment=row,
                    author_name=names.get(row.author_id, "Usuário removido"),
                    attachments=attachments_by_comment.get(row.id, []),
                )
                for row in page
            ],
            total,
            has_more,
        )

    async def update(self, comment_id: uuid.UUID, actor: User, body: str) -> CommentDetail:
        comment = await self._get_editable(comment_id, actor)
        post = await self.posts.get_by_id(comment.post_id)
        post = not_none(post, "a tarefa do comentário está no mesmo tenant, sob o mesmo RLS")
        mentioned = await self._resolve_allowed_mentions(post, body)
        previous = set(comment.mentioned_user_ids)
        comment.body = body
        comment.mentioned_user_ids = mentioned
        # Mesma lição do onupdate server-side (posts/recurrence): sem valor explícito
        # o atributo expira e a leitura síncrona explode com MissingGreenlet.
        comment.updated_at = datetime.now(UTC)
        await self.session.flush()
        # Edição notifica só quem ENTROU na lista — re-mencionar os mesmos não spamma.
        await self._notify_mentions(
            post, comment, actor, [user_id for user_id in mentioned if user_id not in previous]
        )
        return await self._detail(comment)

    async def delete(self, comment_id: uuid.UUID, actor: User) -> None:
        comment = await self._get_editable(comment_id, actor)
        # Regra 4: exclusão é soft — a thread se preserva com "comentário removido".
        comment.deleted_at = datetime.now(UTC)
        comment.updated_at = datetime.now(UTC)
        # Regra 9: excluir o comentário remove os anexos dele.
        await self.attachments.remove_all_for_comment(comment.id)
        await self.session.flush()

    async def _get_editable(self, comment_id: uuid.UUID, actor: User) -> PostComment:
        comment = await self.comments.get_by_id(comment_id)
        if comment is None or comment.deleted_at is not None:
            raise CommentNotFoundError
        if actor.role in _ADMIN_OR_ABOVE:
            return comment
        if comment.author_id != actor.id:
            raise CommentEditForbiddenError
        if datetime.now(UTC) - comment.created_at > _EDIT_WINDOW:
            # Regra 3: passou a janela de 15 min, o próprio autor não edita mais.
            raise CommentEditForbiddenError
        return comment

    async def _attachments_by_comment(
        self, comment_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[Attachment]]:
        """Anexos dos comentários da página em UMA query (sem N+1)."""
        if not comment_ids:
            return {}
        stmt = (
            select(Attachment)
            .where(
                Attachment.attached_to_type == "comment",
                Attachment.attached_to_id.in_(comment_ids),
            )
            .order_by(Attachment.created_at)
        )
        result: dict[uuid.UUID, list[Attachment]] = {cid: [] for cid in comment_ids}
        for attachment in (await self.session.scalars(stmt)).all():
            result[attachment.attached_to_id].append(attachment)
        return result

    async def _detail(self, comment: PostComment) -> CommentDetail:
        author = await self.users.get_by_id(comment.author_id)
        attachments = (
            []
            if comment.deleted_at is not None
            else list(await self.attachments.attachments.list_for("comment", comment.id))
        )
        return CommentDetail(
            comment=comment,
            author_name=author.name if author else "Usuário removido",
            attachments=attachments,
        )
