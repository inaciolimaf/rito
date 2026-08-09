"""PostService (spec 040, alvo 2): depois da divisão, ficam aqui os casos de uso de
LEITURA e EDIÇÃO do post — get, list_for_lawsuit, update, update_flags e delete.
Criação mora em creation.py (CreatePostUseCase); conclusão/reabertura/lida/estrela em
completion.py (CompletePostUseCase); o detalhe montado em detail.py."""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.lawsuits.repository import LawsuitRepository
from app.domain.posts.creation import resolve_assignees, validate_references
from app.domain.posts.detail import AssigneeDetail, PostDetail, build_detail
from app.domain.posts.models import Post
from app.domain.posts.repository import PostRepository
from app.domain.posts.schemas import PostFlagsRequest, PostUpdateRequest
from app.domain.posts.visibility import is_involved
from app.domain.squads.repository import SquadRepository
from app.domain.task_types.repository import TaskTypeRepository
from app.domain.users.repository import UserRepository

__all__ = ["AssigneeDetail", "PostDetail", "PostService"]


def _is_involved(post: Post, assignee_ids: set[uuid.UUID], user_id: uuid.UUID) -> bool:
    """Regra 8: tarefa privada só é visível ao criador e aos responsáveis.
    Alias legado — a função mora em posts/visibility.py (spec 035, regra dos 3 usos)."""
    return is_involved(post, assignee_ids, user_id)


class PostService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.posts = PostRepository(session)
        self.lawsuits = LawsuitRepository(session)
        self.task_types = TaskTypeRepository(session)
        self.squads = SquadRepository(session)
        self.users = UserRepository(session)

    async def get(self, post_id: uuid.UUID, *, viewer_id: uuid.UUID) -> PostDetail | None:
        post = await self.posts.get_by_id(post_id)
        if post is None:
            return None
        # Regra 8: privada invisível para não envolvido — nem GESTOR vê (404, não 403:
        # existir já é informação).
        if post.is_private and not _is_involved(
            post, await self.posts.assignee_ids_for(post.id), viewer_id
        ):
            return None
        return await self._detail(post)

    async def list_for_lawsuit(
        self, lawsuit_id: uuid.UUID, *, viewer_id: uuid.UUID
    ) -> list[PostDetail]:
        posts = await self.posts.list_for_lawsuit(lawsuit_id)
        today = date.today()
        details: list[PostDetail] = []
        lines_by_post = await self.posts.assignee_lines_for([post.id for post in posts])
        names = await self.task_types.names_for({post.task_type_id for post in posts})
        for post in posts:
            # Regra 7: futura fica oculta até a data do compromisso.
            if post.is_future and (post.scheduled_date is None or post.scheduled_date > today):
                continue
            lines = lines_by_post.get(post.id, [])
            if post.is_private and not _is_involved(
                post, {line.user_id for _user, line in lines}, viewer_id
            ):
                # Regra 8: aparece como presença ("tarefa privada"), sem conteúdo.
                details.append(
                    PostDetail(
                        post=post, task_type_name="Tarefa privada", assignees=[], redacted=True
                    )
                )
                continue
            details.append(
                PostDetail(
                    post=post,
                    task_type_name=names[post.task_type_id],
                    assignees=[AssigneeDetail(user=user, line=line) for user, line in lines],
                )
            )
        return details

    async def update(self, post: Post, payload: PostUpdateRequest) -> PostDetail:
        await validate_references(
            lawsuits=self.lawsuits, task_types=self.task_types, payload=payload
        )
        assignee_ids = await resolve_assignees(
            squads=self.squads, users=self.users, user_ids=payload.user_ids, squad_id=None
        )
        post.lawsuit_id = payload.lawsuit_id
        post.task_type_id = payload.task_type_id
        post.scheduled_date = payload.scheduled_date
        post.scheduled_time = None if payload.all_day else payload.scheduled_time
        post.end_date = payload.end_date
        post.end_time = None if payload.all_day else payload.end_time
        post.deadline_date = payload.deadline_date
        post.all_day = payload.all_day
        post.location = payload.location
        post.comments = payload.comments
        # Regra 3: reward_snapshot NÃO é atualizado nem na edição — congelado na criação.
        # `updated_at` tem onupdate server-side: sem valor explícito, o autoflush expira o
        # atributo e a leitura síncrona na resposta explode com MissingGreenlet (mesma
        # lição de LawsuitService.update).
        post.updated_at = datetime.now(UTC)
        await self.posts.replace_assignees(post, assignee_ids)
        return await self._detail(post)

    async def delete(self, post: Post) -> None:
        await self.posts.delete(post)

    async def update_flags(self, post: Post, payload: PostFlagsRequest) -> PostDetail:
        post.is_important = payload.is_important
        post.is_urgent = payload.is_urgent
        post.is_future = payload.is_future
        post.is_private = payload.is_private
        post.show_in_schedule = payload.show_in_schedule
        post.updated_at = datetime.now(UTC)
        return await self._detail(post)

    async def _detail(self, post: Post) -> PostDetail:
        return await build_detail(post, posts=self.posts, task_types=self.task_types)
