import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.inbox.repository import InboxPreferenceRepository, InboxRepository
from app.domain.inbox.sections import DEFAULT_SECTION_ORDER, InboxSection
from app.domain.posts.models import PostUser
from app.domain.posts.repository import PostRepository
from app.domain.posts.service import PostService
from app.domain.users.models import User, UserRole
from app.domain.users.repository import UserRepository

_ADMIN_OR_ABOVE = {UserRole.ADMINISTRADOR, UserRole.GESTOR}


class InvalidSectionError(Exception):
    """Seção fora das 6 da spec — 422."""


class InvalidSectionOrderError(Exception):
    """Regra 9: a ordem precisa ser uma permutação das 6 seções — 422."""


class BulkPartialFailureError(Exception):
    """Regra 6: ação em massa é transacional — a primeira falha aborta tudo e o
    cliente recebe 409 com os ids problemáticos."""

    def __init__(self, failed_ids: list[uuid.UUID], reason: str) -> None:
        super().__init__(reason)
        self.failed_ids = failed_ids
        self.reason = reason


class BulkReassignForbiddenError(Exception):
    """Regra 7: reatribuir em massa exige ADMINISTRADOR."""


class ReassignTargetNotActiveError(Exception):
    """O novo responsável precisa ser usuário ativo do tenant."""


@dataclass
class InboxRow:
    """A linha da caixa de entrada — shape plano, já com partes e responsáveis."""

    post_id: uuid.UUID
    lawsuit_id: uuid.UUID
    task_type_name: str
    scheduled_date: date | None
    scheduled_time: time | None
    deadline_date: date | None
    is_urgent: bool
    is_important: bool
    is_private: bool
    is_read: bool
    is_starred: bool
    created_at: datetime
    parties: list[str] = field(default_factory=list)
    assignee_names: list[str] = field(default_factory=list)


def validate_section_order(order: list[str]) -> list[str]:
    valid = {section.value for section in InboxSection}
    if set(order) != valid or len(order) != len(valid):
        raise InvalidSectionOrderError
    return order


class InboxService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.inbox = InboxRepository(session)
        self.preferences = InboxPreferenceRepository(session)
        self.posts = PostRepository(session)
        self.users = UserRepository(session)

    async def _section_order(self, user_id: uuid.UUID) -> list[str]:
        preference = await self.preferences.get_or_default(user_id, self.tenant_id)
        return list(preference.section_order) or list(DEFAULT_SECTION_ORDER)

    async def list_section(
        self,
        user: User,
        *,
        section: str,
        cursor: tuple[datetime, uuid.UUID] | None,
        limit: int,
    ) -> tuple[list[InboxRow], bool]:
        if section not in {item.value for item in InboxSection}:
            raise InvalidSectionError
        order = await self._section_order(user.id)
        rows = list(
            await self.inbox.list_section(
                user.id,
                section_order=order,
                section=section,
                today=date.today(),
                cursor=cursor,
                limit=limit,
            )
        )
        has_more = len(rows) > limit
        page = rows[:limit]
        parties = await self.inbox.parties_for({row.lawsuit_id for row in page})
        assignees = await self.inbox.assignee_names_for([row.id for row in page])
        return (
            [
                InboxRow(
                    post_id=row.id,
                    lawsuit_id=row.lawsuit_id,
                    task_type_name=row.task_type_name,
                    scheduled_date=row.scheduled_date,
                    scheduled_time=row.scheduled_time,
                    deadline_date=row.deadline_date,
                    is_urgent=row.is_urgent,
                    is_important=row.is_important,
                    is_private=row.is_private,
                    is_read=row.is_read,
                    is_starred=row.is_starred,
                    created_at=row.created_at,
                    parties=parties.get(row.lawsuit_id, []),
                    assignee_names=assignees.get(row.id, []),
                )
                for row in page
            ],
            has_more,
        )

    async def counts(self, user: User) -> dict[str, int]:
        order = await self._section_order(user.id)
        return await self.inbox.counts(user.id, section_order=order, today=date.today())

    async def get_preferences(self, user: User) -> tuple[list[str], list[str], int]:
        preference = await self.preferences.get_or_default(user.id, self.tenant_id)
        return (
            list(preference.section_order),
            list(preference.collapsed_sections),
            preference.page_size,
        )

    async def update_preferences(
        self, user: User, *, section_order: list[str], collapsed_sections: list[str]
    ) -> tuple[list[str], list[str], int]:
        validate_section_order(section_order)
        invalid_collapsed = set(collapsed_sections) - {item.value for item in InboxSection}
        if invalid_collapsed:
            raise InvalidSectionError
        preference = await self.preferences.get_or_default(user.id, self.tenant_id)
        preference.section_order = section_order
        preference.collapsed_sections = collapsed_sections
        await self.session.flush()
        return (
            list(preference.section_order),
            list(preference.collapsed_sections),
            preference.page_size,
        )

    async def _post_users_for(
        self, post_ids: list[uuid.UUID], user_id: uuid.UUID
    ) -> dict[uuid.UUID, PostUser]:
        """A linha do usuário em cada post do lote — a ação em massa opera sempre na
        linha do PRÓPRIO usuário (ele só vê tarefas em que é responsável, regra 3)."""
        lines: dict[uuid.UUID, PostUser] = {}
        for post_id in post_ids:
            line = await self.posts.get_post_user(post_id, user_id)
            if line is not None:
                lines[post_id] = line
        return lines

    async def bulk_complete(self, user: User, post_ids: list[uuid.UUID]) -> None:
        """Regra 6: transacional — conclui a linha do usuário em cada tarefa do lote
        (regras 1 e 2 da 033 valem por linha). Qualquer falha aborta o lote inteiro."""
        lines = await self._post_users_for(post_ids, user.id)
        failed = [post_id for post_id in post_ids if post_id not in lines]
        if failed:
            raise BulkPartialFailureError(failed, "Tarefa fora da sua caixa de entrada.")
        now = datetime.now(UTC)
        for post_id in post_ids:
            line = lines[post_id]
            if line.completed_at is not None:
                continue  # idempotente dentro do lote
            post = await self.posts.get_by_id(post_id)
            assert post is not None
            line.completed_at = now
            line.points_earned = post.reward_snapshot
        await self.session.flush()
        # Regra 1 da 034: a conclusão em massa também dispara a série de recorrência
        # quando a tarefa fecha como um todo.
        post_service = PostService(session=self.session, tenant_id=self.tenant_id)
        for post_id in post_ids:
            post = await self.posts.get_by_id(post_id)
            if (
                post is not None
                and post.recurrence_id is not None
                and await post_service._all_completed(post)
            ):
                await post_service.recurrences.advance_on_completion(post)

    async def bulk_read(self, user: User, post_ids: list[uuid.UUID], *, value: bool) -> None:
        lines = await self._post_users_for(post_ids, user.id)
        failed = [post_id for post_id in post_ids if post_id not in lines]
        if failed:
            raise BulkPartialFailureError(failed, "Tarefa fora da sua caixa de entrada.")
        for line in lines.values():
            line.is_read = value
        await self.session.flush()

    async def bulk_star(self, user: User, post_ids: list[uuid.UUID], *, value: bool) -> None:
        lines = await self._post_users_for(post_ids, user.id)
        failed = [post_id for post_id in post_ids if post_id not in lines]
        if failed:
            raise BulkPartialFailureError(failed, "Tarefa fora da sua caixa de entrada.")
        for line in lines.values():
            line.is_starred = value
        await self.session.flush()

    async def bulk_reassign(
        self, actor: User, post_ids: list[uuid.UUID], *, to_user_id: uuid.UUID
    ) -> None:
        """Regra 7: reatribuir em massa exige ADMINISTRADOR+. Move a linha de TODOS
        os responsáveis atuais para o novo (a caixa é do usuário; a reatribuição é
        da tarefa)."""
        if actor.role not in _ADMIN_OR_ABOVE:
            raise BulkReassignForbiddenError
        target = await self.users.get_by_id(to_user_id)
        if target is None or not target.is_active:
            raise ReassignTargetNotActiveError
        for post_id in post_ids:
            post = await self.posts.get_by_id(post_id)
            if post is None:
                raise BulkPartialFailureError([post_id], "Tarefa não encontrada.")
            await self.posts.replace_assignees(post, [to_user_id])
