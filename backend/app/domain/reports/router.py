import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http import parse_month_query
from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.reports.schemas import (
    AgilityResponse,
    MostDelayedResponse,
    ProductivityResponse,
    WeeklyChartResponse,
)
from app.domain.reports.service import ReportsService
from app.domain.users.models import User

router = APIRouter(prefix="/reports", tags=["reports"])

_DEFAULT_MOST_DELAYED_LIMIT = 10


def _resolve_user_scope(
    current_user: User, requested_user_id: uuid.UUID | None
) -> uuid.UUID | None:
    """Regra 8: Colaborador só vê os próprios números — sem `user_id`, o escopo dele é
    ele mesmo; pedir o `user_id` de outra pessoa é 403. ADMINISTRADOR+ vê todos por
    padrão (`None` = agregado geral) ou filtra por `user_id` à vontade."""
    is_admin = current_user.role in (UserRole.ADMINISTRADOR, UserRole.GESTOR)
    if requested_user_id is not None and requested_user_id != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="Você só pode ver os próprios números.")
    if not is_admin:
        return current_user.id
    return requested_user_id


@router.get("/agility")
async def get_agility_report(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    user_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> AgilityResponse:
    scope_user_id = _resolve_user_scope(current_user, user_id)
    end = to or date.today()
    start = from_ or end.replace(day=1)
    service = ReportsService(session=session, tenant_id=current_user.tenant_id)
    return await service.agility(user_id=scope_user_id, start=start, end=end)


@router.get("/productivity")
async def get_productivity_report(
    month: str | None = Query(default=None),
    user_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> ProductivityResponse:
    scope_user_id = _resolve_user_scope(current_user, user_id)
    month_start = parse_month_query(month)
    service = ReportsService(session=session, tenant_id=current_user.tenant_id)
    return await service.productivity(user_id=scope_user_id, month=month_start)


@router.get("/productivity/weekly")
async def get_productivity_weekly_report(
    user_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> WeeklyChartResponse:
    scope_user_id = _resolve_user_scope(current_user, user_id)
    service = ReportsService(session=session, tenant_id=current_user.tenant_id)
    return await service.productivity_weekly(user_id=scope_user_id, today=date.today())


@router.get("/most-delayed")
async def get_most_delayed_report(
    limit: int = Query(default=_DEFAULT_MOST_DELAYED_LIMIT, ge=1, le=100),
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> MostDelayedResponse:
    service = ReportsService(session=session, tenant_id=current_user.tenant_id)
    return await service.most_delayed(limit=limit)
