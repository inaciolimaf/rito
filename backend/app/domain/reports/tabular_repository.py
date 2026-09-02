"""Consultas dos 9 relatórios tabulares (spec 072) — sempre tempo real (regra 2), sem
view materializada. Nenhuma query filtra tenant no WHERE: todas as tabelas envolvidas
têm RLS (CLAUDE.md §4).
"""

import uuid
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from sqlalchemy import ColumnElement, Date, Row, Select, func, literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.listing import paginate_keyset
from app.domain.action_groups.models import LawsuitType
from app.domain.customer_origins.models import CustomerOrigin
from app.domain.customers.models import Customer
from app.domain.lawsuits.models import Lawsuit, LawsuitOutcome, LawsuitParty, PartyPole
from app.domain.posts.models import Post, PostUser
from app.domain.reports.models import timesheet_daily
from app.domain.task_types.catalog import SYSTEM_TASK_NAMES
from app.domain.task_types.models import TaskType
from app.domain.users.models import User

_HEARING_TASK_TYPE_NAME = SYSTEM_TASK_NAMES[1]  # "Pauta de audiências" (regra 8)


def _parties_label() -> ColumnElement[str]:
    """ "ATIVO x PASSIVO" (regra implícita de exibição, mesma ordem da spec 023)."""
    active = (
        select(func.string_agg(Customer.name, literal(", ")))
        .select_from(LawsuitParty)
        .join(Customer, Customer.id == LawsuitParty.customer_id)
        .where(LawsuitParty.lawsuit_id == Lawsuit.id, LawsuitParty.pole == PartyPole.ATIVO)
        .correlate(Lawsuit)
        .scalar_subquery()
    )
    passive = (
        select(func.string_agg(Customer.name, literal(", ")))
        .select_from(LawsuitParty)
        .join(Customer, Customer.id == LawsuitParty.customer_id)
        .where(LawsuitParty.lawsuit_id == Lawsuit.id, LawsuitParty.pole == PartyPole.PASSIVO)
        .correlate(Lawsuit)
        .scalar_subquery()
    )
    return func.concat(func.coalesce(active, "—"), literal(" x "), func.coalesce(passive, "—"))


class TabularReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _paginate(
        self,
        stmt: Select[Any],
        *,
        sort_column: InstrumentedAttribute[Any] | ColumnElement[Any],
        id_column: InstrumentedAttribute[uuid.UUID],
        cursor: tuple[Any, uuid.UUID] | None,
        limit: int,
        descending: bool = True,
    ) -> tuple[Sequence[Row[Any]], int]:
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        paged = paginate_keyset(
            stmt,
            sort_column=sort_column,
            id_column=id_column,
            descending=descending,
            cursor=cursor,
            limit=limit,
        )
        rows = (await self.session.execute(paged)).all()
        return rows, int(total or 0)

    # ---- productivity / delayed_tasks -------------------------------------------

    def _productivity_base(
        self, *, user_id: uuid.UUID | None, action_group_id: uuid.UUID | None
    ) -> Select[Any]:
        customer_name = (
            select(Customer.name)
            .select_from(LawsuitParty)
            .join(Customer, Customer.id == LawsuitParty.customer_id)
            .where(LawsuitParty.lawsuit_id == Lawsuit.id, LawsuitParty.pole == PartyPole.ATIVO)
            .correlate(Lawsuit)
            .limit(1)
            .scalar_subquery()
        )
        stmt = (
            select(
                Post.id,
                User.name,
                customer_name,
                TaskType.name,
                PostUser.points_earned,
                Post.scheduled_date,
                PostUser.completed_at,
            )
            .select_from(PostUser)
            .join(Post, Post.id == PostUser.post_id)
            .join(TaskType, TaskType.id == Post.task_type_id)
            .join(User, User.id == PostUser.user_id)
            .join(Lawsuit, Lawsuit.id == Post.lawsuit_id)
            .where(Post.is_private.is_(False))
        )
        if user_id is not None:
            stmt = stmt.where(PostUser.user_id == user_id)
        if action_group_id is not None:
            stmt = stmt.join(LawsuitType, LawsuitType.id == Lawsuit.lawsuit_type_id).where(
                LawsuitType.action_group_id == action_group_id
            )
        return stmt

    async def productivity(
        self,
        *,
        user_id: uuid.UUID | None,
        action_group_id: uuid.UUID | None,
        from_: date | None,
        to: date | None,
        cursor: tuple[Any, uuid.UUID] | None,
        limit: int,
    ) -> tuple[Sequence[Row[Any]], int, int]:
        stmt = self._productivity_base(user_id=user_id, action_group_id=action_group_id)
        if from_ is not None:
            stmt = stmt.where(Post.scheduled_date >= from_)
        if to is not None:
            stmt = stmt.where(Post.scheduled_date <= to)
        rows, total = await self._paginate(
            stmt,
            sort_column=Post.scheduled_date,
            id_column=Post.id,
            cursor=cursor,
            limit=limit,
        )
        points_subquery = stmt.with_only_columns(PostUser.points_earned).subquery()
        points_total = await self.session.scalar(
            select(func.coalesce(func.sum(points_subquery.c.points_earned), 0))
        )
        return rows, total, int(points_total or 0)

    async def delayed_tasks(
        self,
        *,
        user_id: uuid.UUID | None,
        action_group_id: uuid.UUID | None,
        from_: date | None,
        to: date | None,
        cursor: tuple[Any, uuid.UUID] | None,
        limit: int,
    ) -> tuple[Sequence[Row[Any]], int, int]:
        customer_name = (
            select(Customer.name)
            .select_from(LawsuitParty)
            .join(Customer, Customer.id == LawsuitParty.customer_id)
            .where(LawsuitParty.lawsuit_id == Lawsuit.id, LawsuitParty.pole == PartyPole.ATIVO)
            .correlate(Lawsuit)
            .limit(1)
            .scalar_subquery()
        )
        delay = (func.cast(PostUser.completed_at, Date) - Post.deadline_date).label("delay_days")
        stmt = (
            select(
                Post.id,
                User.name,
                customer_name,
                TaskType.name,
                PostUser.points_earned,
                Post.scheduled_date,
                delay,
            )
            .select_from(PostUser)
            .join(Post, Post.id == PostUser.post_id)
            .join(TaskType, TaskType.id == Post.task_type_id)
            .join(User, User.id == PostUser.user_id)
            .join(Lawsuit, Lawsuit.id == Post.lawsuit_id)
            .where(
                Post.is_private.is_(False),
                PostUser.completed_at.is_not(None),
                Post.deadline_date.is_not(None),
                func.cast(PostUser.completed_at, Date) > Post.deadline_date,
            )
        )
        if user_id is not None:
            stmt = stmt.where(PostUser.user_id == user_id)
        if action_group_id is not None:
            stmt = stmt.join(LawsuitType, LawsuitType.id == Lawsuit.lawsuit_type_id).where(
                LawsuitType.action_group_id == action_group_id
            )
        if from_ is not None:
            stmt = stmt.where(Post.deadline_date >= from_)
        if to is not None:
            stmt = stmt.where(Post.deadline_date <= to)
        rows, total = await self._paginate(
            stmt, sort_column=delay, id_column=Post.id, cursor=cursor, limit=limit
        )
        points_subquery = stmt.with_only_columns(PostUser.points_earned).subquery()
        points_total = await self.session.scalar(
            select(func.coalesce(func.sum(points_subquery.c.points_earned), 0))
        )
        return rows, total, int(points_total or 0)

    # ---- cadastros ----------------------------------------------------------------

    async def new_customers(
        self,
        *,
        from_: date | None,
        to: date | None,
        cursor: tuple[Any, uuid.UUID] | None,
        limit: int,
    ) -> tuple[Sequence[Row[Any]], int]:
        stmt = (
            select(
                Customer.id,
                Customer.name,
                func.coalesce(Customer.cellphone, Customer.phone, Customer.email),
                func.concat(
                    func.coalesce(Customer.city, "—"),
                    literal("/"),
                    func.coalesce(Customer.state, "—"),
                ),
                CustomerOrigin.name,
                Customer.created_at,
            )
            .select_from(Customer)
            .join(CustomerOrigin, CustomerOrigin.id == Customer.origin_id)
            .where(Customer.is_archived.is_(False))
        )
        if from_ is not None:
            stmt = stmt.where(Customer.created_at >= from_)
        if to is not None:
            stmt = stmt.where(Customer.created_at <= to + timedelta(days=1))
        return await self._paginate(
            stmt, sort_column=Customer.created_at, id_column=Customer.id, cursor=cursor, limit=limit
        )

    # ---- processos ------------------------------------------------------------

    async def new_lawsuits(
        self,
        *,
        user_id: uuid.UUID | None,
        action_group_id: uuid.UUID | None,
        from_: date | None,
        to: date | None,
        cursor: tuple[Any, uuid.UUID] | None,
        limit: int,
    ) -> tuple[Sequence[Row[Any]], int]:
        stmt = (
            select(
                Lawsuit.id,
                _parties_label(),
                LawsuitType.name,
                Lawsuit.process_number,
                User.name,
                Lawsuit.created_at,
            )
            .select_from(Lawsuit)
            .join(LawsuitType, LawsuitType.id == Lawsuit.lawsuit_type_id)
            .join(User, User.id == Lawsuit.user_id)
        )
        if user_id is not None:
            stmt = stmt.where(Lawsuit.user_id == user_id)
        if action_group_id is not None:
            stmt = stmt.where(LawsuitType.action_group_id == action_group_id)
        if from_ is not None:
            stmt = stmt.where(Lawsuit.created_at >= from_)
        if to is not None:
            stmt = stmt.where(Lawsuit.created_at <= to + timedelta(days=1))
        return await self._paginate(
            stmt, sort_column=Lawsuit.created_at, id_column=Lawsuit.id, cursor=cursor, limit=limit
        )

    async def lawsuits_by_outcome(
        self,
        *,
        outcome: LawsuitOutcome,
        user_id: uuid.UUID | None,
        action_group_id: uuid.UUID | None,
        from_: date | None,
        to: date | None,
        cursor: tuple[Any, uuid.UUID] | None,
        limit: int,
    ) -> tuple[Sequence[Row[Any]], int]:
        total_days = (Lawsuit.closure_date - func.cast(Lawsuit.created_at, Date)).label(
            "total_days"
        )
        stmt = (
            select(
                Lawsuit.id,
                _parties_label(),
                LawsuitType.name,
                Lawsuit.process_number,
                Lawsuit.fees_value,
                Lawsuit.closure_date,
                total_days,
            )
            .select_from(Lawsuit)
            .join(LawsuitType, LawsuitType.id == Lawsuit.lawsuit_type_id)
            .where(Lawsuit.outcome == outcome, Lawsuit.closure_date.is_not(None))
        )
        if user_id is not None:
            stmt = stmt.where(Lawsuit.user_id == user_id)
        if action_group_id is not None:
            stmt = stmt.where(LawsuitType.action_group_id == action_group_id)
        if from_ is not None:
            stmt = stmt.where(Lawsuit.closure_date >= from_)
        if to is not None:
            stmt = stmt.where(Lawsuit.closure_date <= to)
        return await self._paginate(
            stmt, sort_column=Lawsuit.closure_date, id_column=Lawsuit.id, cursor=cursor, limit=limit
        )

    # ---- pauta de audiências ----------------------------------------------------

    async def hearings(
        self, *, cursor: tuple[Any, uuid.UUID] | None, limit: int, today: date
    ) -> tuple[Sequence[Row[Any]], int]:
        responsible_name = (
            select(User.name)
            .select_from(PostUser)
            .join(User, User.id == PostUser.user_id)
            .where(PostUser.post_id == Post.id)
            .order_by(User.name)
            .limit(1)
            .correlate(Post)
            .scalar_subquery()
        )
        stmt = (
            select(
                Post.id,
                Post.scheduled_date,
                Post.scheduled_time,
                TaskType.name,
                Lawsuit.process_number,
                _parties_label(),
                Post.location,
                responsible_name,
            )
            .select_from(Post)
            .join(TaskType, TaskType.id == Post.task_type_id)
            .join(Lawsuit, Lawsuit.id == Post.lawsuit_id)
            .where(
                TaskType.name == _HEARING_TASK_TYPE_NAME,
                Post.scheduled_date.is_not(None),
                Post.scheduled_date >= today,
            )
        )
        return await self._paginate(
            stmt,
            sort_column=Post.scheduled_date,
            id_column=Post.id,
            cursor=cursor,
            limit=limit,
            descending=False,
        )

    # ---- partes contrárias --------------------------------------------------------

    async def contrary_parties(
        self, *, cursor: tuple[Any, uuid.UUID] | None, limit: int
    ) -> tuple[Sequence[Row[Any]], int]:
        lawsuit_count = func.count(func.distinct(LawsuitParty.lawsuit_id)).label("lawsuit_count")
        stmt = (
            select(
                Customer.id,
                Customer.name,
                Customer.identification,
                Customer.city,
                lawsuit_count,
            )
            .select_from(LawsuitParty)
            .join(Customer, Customer.id == LawsuitParty.customer_id)
            .where(LawsuitParty.pole == PartyPole.CONTRARIA)
            .group_by(Customer.id, Customer.name, Customer.identification, Customer.city)
        )
        return await self._paginate(
            stmt,
            sort_column=Customer.name,
            id_column=Customer.id,
            cursor=cursor,
            limit=limit,
            descending=False,
        )

    # ---- registro de acesso (spec 073, reaproveitado por 072 regra 5) -----------

    async def access_logs_from_timesheet(
        self, *, cursor: tuple[Any, uuid.UUID] | None, limit: int
    ) -> tuple[Sequence[Row[Any]], int]:
        """`timesheet_daily_visible` é o mesmo agregado por dia do livro de ponto (073)
        — aqui só troca a projeção de colunas. `user_id` não é ORM (é `Table.c`), então
        o keyset é montado à mão em vez de `paginate_keyset` (que exige
        `InstrumentedAttribute` no id_column)."""
        base = (
            select(
                timesheet_daily.c.user_id,
                User.name,
                timesheet_daily.c.day,
                timesheet_daily.c.last_ip,
                timesheet_daily.c.first_access,
                timesheet_daily.c.last_access,
            )
            .select_from(timesheet_daily)
            .join(User, User.id == timesheet_daily.c.user_id)
        )
        total = await self.session.scalar(select(func.count()).select_from(base.subquery()))

        stmt = base.order_by(timesheet_daily.c.day.desc(), timesheet_daily.c.user_id.desc()).limit(
            limit
        )
        if cursor is not None:
            cursor_day, cursor_user_id = cursor
            pair = tuple_(timesheet_daily.c.day, timesheet_daily.c.user_id)
            stmt = stmt.where(pair < tuple_(literal(cursor_day), literal(cursor_user_id)))
        rows = (await self.session.execute(stmt)).all()
        return rows, int(total or 0)
