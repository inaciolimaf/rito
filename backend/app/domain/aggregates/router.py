"""HTTP do registry de agregados (spec 078 §5).

- `GET /aggregates/status` — ADMINISTRADOR (GESTOR entra pela hierarquia, spec 005).
- `POST /aggregates/{name}/refresh` — GESTOR, com throttle de 1 refresh manual por
  agregado a cada 10 min por tenant (regra 8) via Redis (mesmo padrão do recálculo
  de estagnação, spec 052). O refresh executa inline pelo caminho com log
  (`app/workers/aggregates.py`) — falha volta no corpo (`last_error`), nunca como
  erro HTTP (regra 7: dado antigo continua sendo servido).
"""

from contextlib import suppress
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_redis
from app.core.http import get_or_404
from app.core.invariants import not_none
from app.core.permissions import UserRole, require_role
from app.core.rate_limit import check_and_increment
from app.domain.aggregates.schemas import AggregateStatusItem, AggregateStatusResponse
from app.domain.aggregates.service import AggregateService
from app.domain.auth.deps import get_session_for_current_user
from app.domain.users.models import User
from app.workers.aggregates import refresh_aggregate

router = APIRouter(prefix="/aggregates", tags=["aggregates"])

_MANUAL_REFRESH_WINDOW_SECONDS = 600  # regra 8: 1 por agregado a cada 10 min por tenant


@router.get("/status")
async def get_aggregates_status(
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> AggregateStatusResponse:
    service = AggregateService(session)
    return AggregateStatusResponse(items=await service.status(now=datetime.now(UTC)))


@router.post("/{name}/refresh")
async def refresh_aggregate_endpoint(
    name: str,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    redis: Redis = Depends(get_redis),
) -> AggregateStatusItem:
    service = AggregateService(session)
    await get_or_404(
        lambda: service.status_item(name, now=datetime.now(UTC)), "Agregado não encontrado."
    )
    allowed = await check_and_increment(
        redis,
        f"aggregate_manual_refresh:{current_user.tenant_id}:{name}",
        limit=1,
        window_seconds=_MANUAL_REFRESH_WINDOW_SECONDS,
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Refresh manual já foi feito nos últimos 10 minutos para este agregado.",
        )
    # Regra 7: falha de refresh não é erro HTTP — o corpo devolve o estado com
    # `last_error` preenchido e o dado antigo continua sendo servido nas abas.
    with suppress(Exception):
        await refresh_aggregate(name)
    item = await service.status_item(name, now=datetime.now(UTC))
    return not_none(item, "o get_or_404 acima já garantiu que o agregado existe")
