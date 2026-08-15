"""Consultas de registro de acesso e livro de ponto (spec 073).

`list_raw_logs` é tempo real sobre `access_logs` (auditoria por evento); `timesheet_days`
lê a view barreira `timesheet_daily_visible` (matview agregada por dia — migration 073).
"""

import uuid
from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy import Row, func, select

from app.core.listing import paginate_keyset
from app.core.repository import BaseRepository
from app.domain.reports.models import AccessLog, timesheet_daily
from app.domain.users.models import User


class AccessLogRepository(BaseRepository[AccessLog]):
    model = AccessLog

    async def list_raw_logs(
        self,
        *,
        user_id: uuid.UUID | None,
        from_: date | None,
        to: date | None,
        cursor: tuple[Any, uuid.UUID] | None,
        limit: int,
    ) -> tuple[Sequence[Row[Any]], int]:
        stmt = select(AccessLog.id, User.name, AccessLog.ip_address, AccessLog.occurred_at).join(
            User, User.id == AccessLog.user_id
        )
        if user_id is not None:
            stmt = stmt.where(AccessLog.user_id == user_id)
        if from_ is not None:
            stmt = stmt.where(AccessLog.occurred_at >= from_)
        if to is not None:
            stmt = stmt.where(AccessLog.occurred_at <= to)
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        paged = paginate_keyset(
            stmt,
            sort_column=AccessLog.occurred_at,
            id_column=AccessLog.id,
            descending=True,
            cursor=cursor,
            limit=limit,
        )
        rows = (await self.session.execute(paged)).all()
        return rows, int(total or 0)

    async def timesheet_days(
        self, *, user_id: uuid.UUID, start: date, end: date
    ) -> dict[date, Row[Any]]:
        stmt = select(timesheet_daily).where(
            timesheet_daily.c.user_id == user_id,
            timesheet_daily.c.day >= start,
            timesheet_daily.c.day <= end,
        )
        rows = (await self.session.execute(stmt)).all()
        return {row.day: row for row in rows}
