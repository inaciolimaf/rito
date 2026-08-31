import uuid
from collections.abc import Sequence
from typing import cast

from sqlalchemy import ColumnElement, CursorResult, func, select, update
from sqlalchemy.orm import InstrumentedAttribute

from app.core.listing import unaccented_contains
from app.core.repository import BaseRepository
from app.domain.action_groups.models import ActionGroup, LawsuitType


def _same_name(column: InstrumentedAttribute[str], candidate: str) -> ColumnElement[bool]:
    """Regra 1: nome único por tenant, ignorando maiúsculas/minúsculas e acento."""
    return func.unaccent(func.lower(column)) == func.unaccent(func.lower(candidate))


class ActionGroupRepository(BaseRepository[ActionGroup]):
    model = ActionGroup

    async def get_by_name(self, name: str) -> ActionGroup | None:
        result = await self.session.scalars(
            select(ActionGroup).where(_same_name(ActionGroup.name, name))
        )
        return result.first()

    async def list_filtered(
        self, *, is_active: bool | None = None, query: str | None = None
    ) -> Sequence[ActionGroup]:
        stmt = select(ActionGroup).order_by(ActionGroup.name)
        if is_active is not None:
            stmt = stmt.where(ActionGroup.is_active.is_(is_active))
        if query:
            stmt = stmt.where(unaccented_contains(ActionGroup.name, query))
        return (await self.session.scalars(stmt)).all()

    async def count_lawsuit_types(self, group_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
        """Uma query só para a página inteira — evita N+1 (mesmo padrão de squads, 013)."""
        if not group_ids:
            return {}
        rows = (
            await self.session.execute(
                select(LawsuitType.action_group_id, func.count())
                .where(LawsuitType.action_group_id.in_(group_ids))
                .group_by(LawsuitType.action_group_id)
            )
        ).all()
        counts = {group_id: 0 for group_id in group_ids}
        for group_id, count in rows:
            counts[group_id] = count
        return counts


class LawsuitTypeRepository(BaseRepository[LawsuitType]):
    model = LawsuitType

    async def get_by_name(self, name: str) -> LawsuitType | None:
        result = await self.session.scalars(
            select(LawsuitType).where(_same_name(LawsuitType.name, name))
        )
        return result.first()

    async def list_filtered(
        self,
        *,
        action_group_id: uuid.UUID | None = None,
        is_active: bool | None = None,
        query: str | None = None,
    ) -> Sequence[LawsuitType]:
        stmt = select(LawsuitType).order_by(LawsuitType.name)
        if action_group_id is not None:
            stmt = stmt.where(LawsuitType.action_group_id == action_group_id)
        if is_active is not None:
            stmt = stmt.where(LawsuitType.is_active.is_(is_active))
        if query:
            stmt = stmt.where(unaccented_contains(LawsuitType.name, query))
        return (await self.session.scalars(stmt)).all()

    async def reassign_group(self, *, from_group_id: uuid.UUID, to_group_id: uuid.UUID) -> int:
        """Regra 3/7: transferência transacional — reatribui todos os tipos do grupo de
        origem para o destino. Uma única query, tudo ou nada (o commit é da sessão da
        requisição, não daqui)."""
        result = await self.session.execute(
            update(LawsuitType)
            .where(LawsuitType.action_group_id == from_group_id)
            .values(action_group_id=to_group_id)
        )
        # execute() de um UPDATE Core devolve um CursorResult de verdade em runtime — o
        # tipo genérico Result[Any] só não expõe `rowcount` estaticamente.
        return cast(CursorResult[tuple[()]], result).rowcount
