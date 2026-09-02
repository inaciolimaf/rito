"""Criação de posts (spec 040, alvo 2 — CreatePostUseCase): validação de referências,
expansão de time (squad), detecção de duplicata e o reward_snapshot congelado.

`resolve_assignees`/`validate_references` são funções de módulo de propósito — o
update (PostService) precisa das mesmas validações e não devia depender do use case
inteiro para isso."""

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.invariants import not_none
from app.domain.lawsuits.repository import LawsuitRepository
from app.domain.posts.detail import PostDetail, build_detail
from app.domain.posts.exceptions import (
    AssigneeNotActiveError,
    DuplicatePostError,
    LawsuitNotFoundError,
    SquadNotFoundError,
    TaskTypeNotFoundError,
)
from app.domain.posts.models import Post
from app.domain.posts.recurrence_service import RecurrenceService
from app.domain.posts.repository import PostRepository
from app.domain.posts.schemas import PostCreateRequest, PostUpdateRequest
from app.domain.squads.repository import SquadRepository
from app.domain.task_types.models import TaskType
from app.domain.task_types.repository import TaskTypeRepository
from app.domain.users.models import User
from app.domain.users.repository import UserRepository


async def resolve_assignees(
    *,
    squads: SquadRepository,
    users: UserRepository,
    user_ids: Sequence[uuid.UUID],
    squad_id: uuid.UUID | None,
) -> list[uuid.UUID]:
    """Regra 2: squad expande para os membros ATIVOS no momento da criação (o time
    não fica vinculado). Regra 1: ≥1 responsável DEPOIS da expansão."""
    resolved = list(dict.fromkeys(user_ids))
    if squad_id is not None:
        squad = await squads.get_by_id(squad_id)
        if squad is None:
            raise SquadNotFoundError
        members = await squads.get_members(squad_id)
        resolved += [member.id for member in members if member.is_active]
        resolved = list(dict.fromkeys(resolved))
    if not resolved:
        raise AssigneeNotActiveError
    for user_id in resolved:
        user = await users.get_by_id(user_id)
        # Regra 9: todo responsável precisa ser usuário ativo do tenant.
        if user is None or not user.is_active:
            raise AssigneeNotActiveError
    return resolved


async def validate_references(
    *,
    lawsuits: LawsuitRepository,
    task_types: TaskTypeRepository,
    payload: PostCreateRequest | PostUpdateRequest,
) -> None:
    if await lawsuits.get_by_id(payload.lawsuit_id) is None:
        raise LawsuitNotFoundError
    if await task_types.get_by_id(payload.task_type_id) is None:
        raise TaskTypeNotFoundError


class CreatePostUseCase:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.tenant_id = tenant_id
        self.posts = PostRepository(session)
        self.lawsuits = LawsuitRepository(session)
        self.task_types = TaskTypeRepository(session)
        self.squads = SquadRepository(session)
        self.users = UserRepository(session)
        self.recurrences = RecurrenceService(session, tenant_id)

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

    def _post_from(self, payload: PostCreateRequest, author: User, task_type: TaskType) -> Post:
        """A tarefa a partir do pedido, com as duas regras que não são cópia.

        Regra 10: `all_day` IGNORA os campos de hora — guardar a hora de um evento de dia
        inteiro faria a agenda mostrar um horário que o usuário não escolheu.

        Regra 3: a pontuação do catálogo é CONGELADA na criação. Se o escritório mudar o
        valor do tipo de tarefa depois, quem já cumpriu mantém o que valia na época — sem
        isso, o ranking do mês passado mudaria sozinho.
        """
        return Post(
            tenant_id=self.tenant_id,
            lawsuit_id=payload.lawsuit_id,
            task_type_id=payload.task_type_id,
            created_by=author.id,
            scheduled_date=payload.scheduled_date,
            scheduled_time=None if payload.all_day else payload.scheduled_time,
            end_date=payload.end_date,
            end_time=None if payload.all_day else payload.end_time,
            deadline_date=payload.deadline_date,
            all_day=payload.all_day,
            location=payload.location,
            comments=payload.comments,
            reward_snapshot=task_type.reward,
            is_important=payload.is_important,
            is_urgent=payload.is_urgent,
            is_future=payload.is_future,
            is_private=payload.is_private,
            show_in_schedule=payload.show_in_schedule,
        )

    async def create(self, payload: PostCreateRequest, author: User) -> PostDetail:
        await validate_references(
            lawsuits=self.lawsuits, task_types=self.task_types, payload=payload
        )
        assignee_ids = await resolve_assignees(
            squads=self.squads,
            users=self.users,
            user_ids=payload.user_ids,
            squad_id=payload.squad_id,
        )
        await self._check_duplicate(payload, assignee_ids)
        task_type = await self.task_types.get_by_id(payload.task_type_id)
        task_type = not_none(task_type, "validado em validate_references")
        post = self._post_from(payload, author, task_type)
        created = await self.posts.create_with_assignees(post, assignee_ids)
        if payload.recurrence is not None:
            # Spec 034: o post criado é o template (e a 1ª ocorrência) da série.
            await self.recurrences.create_series(created, payload.recurrence)
        return await build_detail(created, posts=self.posts, task_types=self.task_types)
