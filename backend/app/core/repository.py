import base64
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.models import Base

# Separador improvável de aparecer num valor de ordenação real (nome, e-mail...) — usado
# só para não confundir o valor com o UUID no cursor decodificado.
_CURSOR_SEPARATOR = "\x1f"


def encode_cursor(sort_value: str, id_: uuid.UUID) -> str:
    """Cursor opaco em base64 (CLAUDE.md §6) — codifica `(sort_value, id)`, nunca só o id,
    para paginar corretamente quando o valor de ordenação se repete entre linhas."""
    raw = f"{sort_value}{_CURSOR_SEPARATOR}{id_}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[str, uuid.UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    sort_value, _, id_str = raw.rpartition(_CURSOR_SEPARATOR)
    return sort_value, uuid.UUID(id_str)


def build_sorted_keyset_query[ModelT: Base](
    model: type[ModelT],
    *,
    sort_column: InstrumentedAttribute[Any],
    cursor: tuple[str, uuid.UUID] | None,
    limit: int,
) -> Select[tuple[ModelT]]:
    """Keyset ordenado por uma coluna escolhida (ex.: nome), com `id` como desempate —
    contrato de listagem do CLAUDE.md §6. Diferente de `build_keyset_query` (ordena só por
    `id`, mantido como está para não mexer no que a spec 010 já cobre): aqui a página
    seguinte usa `WHERE (sort_column, id) > (cursor_value, cursor_id)`, o que faz o
    desempate por `id` funcionar mesmo quando o valor de ordenação se repete (dois usuários
    com o mesmo nome, por exemplo) — comparação de tupla, não duas cláusulas independentes.
    """
    stmt = select(model).order_by(sort_column, model.id).limit(limit)
    if cursor is not None:
        cursor_value, cursor_id = cursor
        # literal(): tuple_() do lado direito da comparação espera ColumnElement, não
        # valores Python crus — sem isso o mypy (corretamente) recusa passar str/UUID.
        stmt = stmt.where(
            tuple_(sort_column, model.id) > tuple_(literal(cursor_value), literal(cursor_id))
        )
    return stmt


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
