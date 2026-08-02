import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.lawsuits.repository import LawsuitRepository
from app.domain.posts.exceptions import (
    AssigneeNotActiveError,
    DuplicatePostError,
    LawsuitNotFoundError,
    SquadNotFoundError,
    TaskTypeNotFoundError,
)
from app.domain.posts.models import Post
from app.domain.posts.repository import PostRepository
from app.domain.posts.schemas import PostCreateRequest, PostUpdateRequest
from app.domain.squads.repository import SquadRepository
from app.domain.task_types.repository import TaskTypeRepository
from app.domain.users.models import User
from app.domain.users.repository import UserRepository


@dataclass
class PostDetail:
    post: Post
    task_type_name: str
    assignees: Sequence[User]


class PostService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.posts = PostRepository(session)
        self.lawsuits = LawsuitRepository(session)
        self.task_types = TaskTypeRepository(session)
        self.squads = SquadRepository(session)
        self.users = UserRepository(session)

    async def _resolve_assignees(
        self, *, user_ids: Sequence[uuid.UUID], squad_id: uuid.UUID | None
    ) -> list[uuid.UUID]:
        """Regra 2: squad expande para os membros ATIVOS no momento da criação (o time
        não fica vinculado). Regra 1: ≥1 responsável DEPOIS da expansão."""
        resolved = list(dict.fromkeys(user_ids))
        if squad_id is not None:
            squad = await self.squads.get_by_id(squad_id)
            if squad is None:
                raise SquadNotFoundError
            members = await self.squads.get_members(squad_id)
            resolved += [member.id for member in members if member.is_active]
            resolved = list(dict.fromkeys(resolved))
        if not resolved:
            raise AssigneeNotActiveError
        for user_id in resolved:
            user = await self.users.get_by_id(user_id)
            # Regra 9: todo responsável precisa ser usuário ativo do tenant.
            if user is None or not user.is_active:
                raise AssigneeNotActiveError
        return resolved

    async def _validate_references(self, payload: PostCreateRequest | PostUpdateRequest) -> None:
        if await self.lawsuits.get_by_id(payload.lawsuit_id) is None:
            raise LawsuitNotFoundError
        if await self.task_types.get_by_id(payload.task_type_id) is None:
            raise TaskTypeNotFoundError

    async def _check_duplicate(
        self, payload: PostCreateRequest, assignee_ids: Sequence[uuid.UUID]
    ) -> None:
        """Regra 4: mesmo processo + tipo + data + mesmo CONJUNTO de responsáveis."""
        candidates = await self.posts.find_duplicates(
            lawsuit_id=payload.lawsuit_id,
            task_type_id=payload.task_type_id,
            scheduled_date=payload.scheduled_date,
        )
        wanted = set(assignee_ids)
        for candidate in candidates:
            if await self.posts.assignee_ids_for(candidate.id) == wanted:
                raise DuplicatePostError(candidate.id)

    async def create(self, payload: PostCreateRequest, author: User) -> PostDetail:
        await self._validate_references(payload)
        assignee_ids = await self._resolve_assignees(
            user_ids=payload.user_ids, squad_id=payload.squad_id
        )
        await self._check_duplicate(payload, assignee_ids)
        task_type = await self.task_types.get_by_id(payload.task_type_id)
        assert task_type is not None  # validado em _validate_references
        post = Post(
            tenant_id=self.tenant_id,
            lawsuit_id=payload.lawsuit_id,
            task_type_id=payload.task_type_id,
            created_by=author.id,
            scheduled_date=payload.scheduled_date,
            # Regra 10: all_day ignora os campos de hora.
            scheduled_time=None if payload.all_day else payload.scheduled_time,
            end_date=payload.end_date,
            end_time=None if payload.all_day else payload.end_time,
            deadline_date=payload.deadline_date,
            all_day=payload.all_day,
            location=payload.location,
            comments=payload.comments,
            # Regra 3: congela a pontuação do catálogo na criação — nunca muda depois.
            reward_snapshot=task_type.reward,
        )
        created = await self.posts.create_with_assignees(post, assignee_ids)
        return await self._detail(created)

    async def get(self, post_id: uuid.UUID) -> PostDetail | None:
        post = await self.posts.get_by_id(post_id)
        if post is None:
            return None
        return await self._detail(post)

    async def list_for_lawsuit(self, lawsuit_id: uuid.UUID) -> list[PostDetail]:
        posts = await self.posts.list_for_lawsuit(lawsuit_id)
        assignees = await self.posts.assignees_for([post.id for post in posts])
        names = await self.task_types.names_for({post.task_type_id for post in posts})
        return [
            PostDetail(
                post=post,
                task_type_name=names[post.task_type_id],
                assignees=assignees.get(post.id, []),
            )
            for post in posts
        ]

    async def update(self, post: Post, payload: PostUpdateRequest) -> PostDetail:
        await self._validate_references(payload)
        assignee_ids = await self._resolve_assignees(user_ids=payload.user_ids, squad_id=None)
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

    async def _detail(self, post: Post) -> PostDetail:
        task_type = await self.task_types.get_by_id(post.task_type_id)
        assert task_type is not None
        assignees = await self.posts.assignees_for([post.id])
        return PostDetail(
            post=post, task_type_name=task_type.name, assignees=assignees.get(post.id, [])
        )
