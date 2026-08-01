import uuid
from collections.abc import Sequence

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Base


def build_keyset_query[ModelT: Base](
    model: type[ModelT], *, cursor: uuid.UUID | None, limit: int
) -> Select[tuple[ModelT]]:
    """Statement de listagem paginada por keyset, ordenada por `id`.

    Função pura (não executa nada) para ser testável sem banco de dados.
    """
    stmt = select(model).order_by(model.id).limit(limit)
    if cursor is not None:
        stmt = stmt.where(model.id > cursor)
    return stmt


class BaseRepository[ModelT: Base]:
    """CRUD genérico. Todo repositório de domínio herda daqui (CLAUDE.md §6)."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, id_: uuid.UUID) -> ModelT | None:
        return await self.session.get(self.model, id_)

    async def list_paginated(
        self, *, limit: int = 20, cursor: uuid.UUID | None = None
    ) -> Sequence[ModelT]:
        stmt = build_keyset_query(self.model, cursor=cursor, limit=limit)
        result = await self.session.scalars(stmt)
        return result.all()

    async def create(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def delete(self, instance: ModelT) -> None:
        await self.session.delete(instance)
