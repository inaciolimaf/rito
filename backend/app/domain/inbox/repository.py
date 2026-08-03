import uuid
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from sqlalchemy import Row, String, case, cast, func, literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.repository import BaseRepository
from app.domain.customers.models import Customer
from app.domain.inbox.models import InboxPreference
from app.domain.inbox.sections import (
    DEADLINE_HORIZON_DAYS,
    PUBLICATIONS_TASK_TYPE_NAME,
    InboxSection,
)
from app.domain.lawsuits.models import LawsuitParty
from app.domain.posts.models import Post, PostUser
from app.domain.task_types.models import TaskType
from app.domain.users.models import User


class InboxPreferenceRepository(BaseRepository[InboxPreference]):
    model = InboxPreference

    async def get_or_default(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> InboxPreference:
        """Regra 9: a preferência é por usuário; a primeira leitura materializa o
        default (a linha existe para o PUT seguinte)."""
        stmt = select(InboxPreference).where(InboxPreference.user_id == user_id)
        preference = (await self.session.scalars(stmt)).first()
        if preference is None:
            preference = InboxPreference(tenant_id=tenant_id, user_id=user_id)
            self.session.add(preference)
            await self.session.flush()
        return preference


def _inbox_subquery(user_id: uuid.UUID, today: date) -> Any:
    """O escopo da caixa de entrada (regras 3, 4, 5) como subquery: só tarefas em que
    o usuário é responsável, ainda não concluídas POR ELE, futuras só depois da data.
    Tarefa privada de terceiro nunca chega aqui — o usuário não é responsável por ela.
    """
    return (
        select(
            Post,
            TaskType.name.label("task_type_name"),
            PostUser.is_read,
            PostUser.is_starred,
        )
        .join(PostUser, (PostUser.post_id == Post.id) & (PostUser.user_id == user_id))
        .join(TaskType, TaskType.id == Post.task_type_id)
        .where(
            PostUser.completed_at.is_(None),  # regra 5: concluída sai da caixa
            # Regra 4: futura fica oculta até a data do compromisso.
            (Post.is_future.is_(False))
            | (Post.scheduled_date.is_not(None) & (Post.scheduled_date <= today)),
        )
        .subquery()
    )


def _section_case(sub: Any, section_order: Sequence[str], today: date) -> ColumnElement[str]:
    """CASE WHEN na ordem configurada — a PRIMEIRA seção que casa vence (regra 1).
    Os predicados são a regra 2 escrita em SQL."""
    deadline_cutoff = date.fromordinal(today.toordinal() + DEADLINE_HORIZON_DAYS)
    predicates = {
        InboxSection.DEADLINE.value: (sub.c.deadline_date.is_not(None))
        & (sub.c.deadline_date <= deadline_cutoff),
        InboxSection.PUBLICATIONS.value: sub.c.task_type_name == PUBLICATIONS_TASK_TYPE_NAME,
        InboxSection.UNREAD.value: sub.c.is_read.is_(False),
        InboxSection.URGENT.value: sub.c.is_urgent.is_(True),
        InboxSection.IMPORTANT.value: sub.c.is_important.is_(True),
    }
    whens = [
        (predicates[section], section)
        for section in section_order
        if section != InboxSection.OTHERS.value
    ]
    return cast(case(*whens, else_=InboxSection.OTHERS.value), String)


class InboxRepository:
    """Consultas da caixa de entrada — não é BaseRepository (não há modelo próprio;
    a seção é derivada do Post por CASE na ordem configurada)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_section(
        self,
        user_id: uuid.UUID,
        *,
        section_order: Sequence[str],
        section: str,
        today: date,
        cursor: tuple[datetime, uuid.UUID] | None,
        limit: int,
    ) -> Sequence[Row[Any]]:
        """Regra 10: keyset por (created_at, id) independente por seção."""
        sub = _inbox_subquery(user_id, today)
        stmt = (
            select(sub)
            .where(_section_case(sub, section_order, today) == section)
            .order_by(sub.c.created_at, sub.c.id)
            .limit(limit + 1)
        )
        if cursor is not None:
            cursor_value, cursor_id = cursor
            stmt = stmt.where(
                tuple_(sub.c.created_at, sub.c.id)
                > tuple_(literal(cursor_value), literal(cursor_id))
            )
        return (await self.session.execute(stmt)).all()

    async def counts(
        self, user_id: uuid.UUID, *, section_order: Sequence[str], today: date
    ) -> dict[str, int]:
        """Regra 8: UMA query para as 6 seções — GROUP BY sobre o CASE, sem loop."""
        sub = _inbox_subquery(user_id, today)
        section_expr = _section_case(sub, section_order, today)
        stmt = (
            select(section_expr.label("section"), func.count())
            .select_from(sub)
            .group_by(section_expr)
        )
        result = {section.value: 0 for section in InboxSection}
        for section_value, count in await self.session.execute(stmt):
            result[str(section_value)] = int(count)
        return result

    async def parties_for(self, lawsuit_ids: set[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        """Partes dos processos da página em UMA query (sem N+1), polo/nome como na
        listagem de processos."""
        if not lawsuit_ids:
            return {}
        stmt = (
            select(LawsuitParty.lawsuit_id, Customer.name)
            .join(Customer, Customer.id == LawsuitParty.customer_id)
            .where(LawsuitParty.lawsuit_id.in_(lawsuit_ids))
            .order_by(LawsuitParty.lawsuit_id, LawsuitParty.pole, Customer.name)
        )
        result: dict[uuid.UUID, list[str]] = {lawsuit_id: [] for lawsuit_id in lawsuit_ids}
        for lawsuit_id, name in await self.session.execute(stmt):
            result[lawsuit_id].append(str(name))
        return result

    async def assignee_names_for(self, post_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        """Responsáveis das tarefas da página em UMA query (sem N+1)."""
        if not post_ids:
            return {}
        stmt = (
            select(PostUser.post_id, User.name)
            .join(User, User.id == PostUser.user_id)
            .where(PostUser.post_id.in_(post_ids))
            .order_by(User.name)
        )
        result: dict[uuid.UUID, list[str]] = {post_id: [] for post_id in post_ids}
        for post_id, name in await self.session.execute(stmt):
            result[post_id].append(str(name))
        return result
