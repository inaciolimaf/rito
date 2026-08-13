import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import ColumnElement, func, select

from app.core.listing import paginate_keyset
from app.core.repository import BaseRepository
from app.domain.templates.models import Template, TemplateType


class TemplateRepository(BaseRepository[Template]):
    model = Template

    def _view_filters(self, view: str) -> list[ColumnElement[bool]]:
        if view == "trash":
            return [Template.deleted_at.is_not(None)]
        filters: list[ColumnElement[bool]] = [Template.deleted_at.is_(None)]
        if view != "all":
            filters.append(Template.type == TemplateType(view))
        return filters

    async def list_filtered(
        self,
        *,
        view: str,
        query: str | None,
        cursor: tuple[datetime, uuid.UUID] | None,
        limit: int,
    ) -> tuple[Sequence[Template], int]:
        filters = self._view_filters(view)
        if query:
            filters.append(Template.name.ilike(f"%{query}%"))

        count_stmt = select(func.count()).select_from(Template)
        for condition in filters:
            count_stmt = count_stmt.where(condition)
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = select(Template)
        for condition in filters:
            stmt = stmt.where(condition)
        stmt = paginate_keyset(
            stmt,
            sort_column=Template.created_at,
            id_column=Template.id,
            descending=True,
            cursor=cursor,
            limit=limit,
        )
        items = (await self.session.scalars(stmt)).all()
        return items, total
