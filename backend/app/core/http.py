import re
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Literal

from fastapi import HTTPException

_MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


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


def parse_month_query(month: str | None) -> date:
    """`?month=YYYY-MM` → dia 1 do mês (ou o mês corrente se omitido) — repetido em
    todo filtro de período mensal (`lawsuits/stats`, spec 028; `transactions/stats` e
    `/chart`, spec 059; extraído na refatoração 060, Alvo "duplicação")."""
    if month is None:
        return date.today().replace(day=1)
    if not _MONTH_PATTERN.fullmatch(month):
        raise HTTPException(status_code=422, detail="Mês inválido — use YYYY-MM.")
    return date.fromisoformat(f"{month}-01")
