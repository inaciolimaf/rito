from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import HTTPException


async def get_or_404[T](getter: Callable[[], Awaitable[T | None]], detail: str) -> T:
    """`get-or-404` repetido em todo router com GET/PUT/DELETE por id (spec 020, pente-fino
    de duplicação) — `getter` é o `service.get(id)` de cada domínio."""
    found = await getter()
    if found is None:
        raise HTTPException(status_code=404, detail=detail)
    return found


def parse_active_status(status_: Literal["active", "inactive"] | None) -> bool | None:
    """`?status=active|inactive` → `is_active` booleano, repetido em todo router de
    taxonomia simples (customer_origins, action_groups, lawsuit_types, stages, squads)."""
    return {"active": True, "inactive": False}.get(status_) if status_ else None
