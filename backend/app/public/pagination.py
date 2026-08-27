"""Paginação da API pública (spec 095, regra 8).

Cursor, nunca offset — a mesma decisão do CLAUDE.md §6, pelo mesmo motivo: offset quebra
em volume, e é justamente o integrador que varre a base inteira quem sofre primeiro.
"""

from dataclasses import dataclass
from typing import Any

from fastapi import Query

from app.public.deps import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE


@dataclass(frozen=True)
class Page[T]:
    items: list[T]
    next_cursor: str | None
    total: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"items": self.items, "next_cursor": self.next_cursor, "total": self.total}


def limit_param() -> Any:
    return Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
