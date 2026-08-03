import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.lawsuits.repository import LawsuitRepository
from app.domain.posts.exceptions import (
    AssigneeNotActiveError,
    CompleteForOthersForbiddenError,
    DuplicatePostError,
    FutureCompletionError,
    LawsuitNotFoundError,
    NotAssigneeError,
    SquadNotFoundError,
    TaskTypeNotFoundError,
)
from app.domain.posts.models import Post, PostUser
from app.domain.posts.recurrence_service import RecurrenceService
from app.domain.posts.repository import PostRepository
from app.domain.posts.schemas import (
    PostCompleteRequest,
    PostCreateRequest,
    PostFlagsRequest,
    PostReopenRequest,
    PostUpdateRequest,
)
from app.domain.posts.visibility import is_involved
from app.domain.squads.repository import SquadRepository
from app.domain.task_types.repository import TaskTypeRepository
from app.domain.users.models import User, UserRole
from app.domain.users.repository import UserRepository

# Regra 9: ADMINISTRADOR (ou acima) pode concluir pela linha de outro responsável.
_ADMIN_OR_ABOVE = {UserRole.ADMINISTRADOR, UserRole.GESTOR}


@dataclass
class AssigneeDetail:
    user: User
    line: PostUser


@dataclass
class PostDetail:
    post: Post
    task_type_name: str
    assignees: Sequence[AssigneeDetail]
    # Regra 8: tarefa privada para não envolvido — presença sem conteúdo.
    redacted: bool = False


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
        self.recurrences = RecurrenceService(session, tenant_id)

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
            is_important=payload.is_important,
            is_urgent=payload.is_urgent,
            is_future=payload.is_future,
            is_private=payload.is_private,
            show_in_schedule=payload.show_in_schedule,
        )
        created = await self.posts.create_with_assignees(post, assignee_ids)
        if payload.recurrence is not None:
            # Spec 034: o post criado é o template (e a 1ª ocorrência) da série.
            await self.recurrences.create_series(created, payload.recurrence)
        return await self._detail(created)

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

    async def update_flags(self, post: Post, payload: PostFlagsRequest) -> PostDetail:
        post.is_important = payload.is_important
        post.is_urgent = payload.is_urgent
        post.is_future = payload.is_future
        post.is_private = payload.is_private
        post.show_in_schedule = payload.show_in_schedule
        post.updated_at = datetime.now(UTC)
        return await self._detail(post)

    async def _resolve_completion_line(
        self, post: Post, actor: User, target_user_id: uuid.UUID | None
    ) -> tuple[PostUser, bool]:
        """Targeting comum de complete/reopen: devolve (linha, por_terceiro)."""
        target_id = target_user_id or actor.id
        by_other = target_id != actor.id
        if by_other and actor.role not in _ADMIN_OR_ABOVE:
            # Regra 9: só ADMINISTRADOR+ conclui/reabre pela linha de outro.
            raise CompleteForOthersForbiddenError
        line = await self.posts.get_post_user(post.id, target_id)
        if line is None:
            # Regra 9: só quem é responsável tem linha para concluir.
            raise NotAssigneeError
        return line, by_other

    async def complete(self, post: Post, actor: User, payload: PostCompleteRequest) -> PostDetail:
        line, by_other = await self._resolve_completion_line(post, actor, payload.user_id)
        if line.completed_at is not None:
            return await self._detail(post)  # idempotente: já concluída, sem efeito
        completed_at = payload.completed_at or datetime.now(UTC)
        # Regra 4: retroativa permite o passado, NUNCA o futuro.
        if completed_at > datetime.now(UTC):
            raise FutureCompletionError
        line.completed_at = completed_at
        # Regra 2: os pontos creditados são o reward_snapshot do post — congelado ali.
        # Regra 5: retroativa credita na competência da data informada — completed_at
        # guarda a data informada, não "agora".
        line.points_earned = post.reward_snapshot
        # Regra 9: ADMIN concluindo por outro fica registrado em completed_by.
        line.completed_by = actor.id if by_other else None
        if post.recurrence_id is not None and await self._all_completed(post):
            # Spec 034, regra 1: a série gera a próxima ocorrência ao concluir a
            # atual como um todo (todos os responsáveis).
            await self.recurrences.advance_on_completion(post)
        return await self._detail(post)

    async def _all_completed(self, post: Post) -> bool:
        lines = await self.posts.lines_for_post(post.id)
        return all(item.completed_at is not None for item in lines)

    async def reopen(self, post: Post, actor: User, payload: PostReopenRequest) -> PostDetail:
        line, _by_other = await self._resolve_completion_line(post, actor, payload.user_id)
        # Regra 6: reabrir zera conclusão e pontos daquele responsável.
        line.completed_at = None
        line.points_earned = None
        line.completed_by = None
        return await self._detail(post)

    async def set_read(self, post: Post, actor: User, *, value: bool) -> PostDetail:
        line = await self.posts.get_post_user(post.id, actor.id)
        if line is None:
            raise NotAssigneeError
        # Regra 11: lida é por usuário, não da tarefa.
        line.is_read = value
        return await self._detail(post)

    async def set_starred(self, post: Post, actor: User, *, value: bool) -> PostDetail:
        line = await self.posts.get_post_user(post.id, actor.id)
        if line is None:
            raise NotAssigneeError
        # Regra 11: estrela é por usuário, não da tarefa.
        line.is_starred = value
        return await self._detail(post)

    async def _detail(self, post: Post) -> PostDetail:
        task_type = await self.task_types.get_by_id(post.task_type_id)
        assert task_type is not None
        lines = await self.posts.assignee_lines_for([post.id])
        return PostDetail(
            post=post,
            task_type_name=task_type.name,
            assignees=[
                AssigneeDetail(user=user, line=line) for user, line in lines.get(post.id, [])
            ],
        )
