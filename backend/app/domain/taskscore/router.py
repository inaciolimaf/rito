import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock
from app.core.deps import get_redis
from app.core.http import get_or_404
from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_clock, get_session_for_current_user
from app.domain.lawsuits.stats import invalidate_stats_cache
from app.domain.taskscore.exceptions import ActionGroupNotFoundError
from app.domain.taskscore.schemas import (
    ClosureGoalsListResponse,
    ClosureGoalsPutRequest,
    MyScoreResponse,
    RankingResponse,
    ScoreChartResponse,
    parse_month,
)
from app.domain.taskscore.service import RankingSort, TaskscoreService
from app.domain.users.models import User
from app.domain.users.service import UserService

goals_router = APIRouter(prefix="/goals", tags=["goals"])
taskscore_router = APIRouter(prefix="/taskscore", tags=["taskscore"])


def _parse_period(period: str | None) -> date | None:
    """ "YYYY-MM" → date do mês; "eltv" → None (None = ELTV nas queries, regra 5)."""
    if period is None or period == "eltv":
        return None
    try:
        return parse_month(period)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="Período inválido — use YYYY-MM ou 'eltv'."
        ) from exc


@goals_router.get("/closures")
async def list_closure_goals(
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> ClosureGoalsListResponse:
    service = TaskscoreService(session=session, tenant_id=current_user.tenant_id)
    return ClosureGoalsListResponse(items=await service.list_closure_goals())


@goals_router.put("/closures")
async def put_closure_goals(
    payload: ClosureGoalsPutRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    redis: Redis = Depends(get_redis),
    clock: Clock = Depends(get_clock),
) -> ClosureGoalsListResponse:
    service = TaskscoreService(session=session, tenant_id=current_user.tenant_id)
    try:
        await service.put_closure_goals(payload.items)
    except ActionGroupNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Grupo de ação não encontrado.") from exc
    # A meta alimenta o widget da spec 028 (regra 8), que tem cache de 5 min — mudar a
    # meta derruba o cache do mês corrente para o widget refletir na hora.
    await invalidate_stats_cache(redis, current_user.tenant_id, today=clock.today())
    return ClosureGoalsListResponse(items=await service.list_closure_goals())


@taskscore_router.get("/me")
async def my_score(
    period: str | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    clock: Clock = Depends(get_clock),
) -> MyScoreResponse:
    """Regra 6: qualquer colaborador vê o PRÓPRIO desempenho."""
    # Período omitido = mês corrente (default do painel); "eltv" vira None = vida toda.
    # Spec 114: o mês corrente é o do escritório — em Rio Branco, virar o mês três horas
    # antes do servidor é a diferença entre a pontuação cair no mês certo ou no seguinte.
    hoje = clock.today()
    month = _parse_period(period) if period else hoje.replace(day=1)
    service = TaskscoreService(session=session, tenant_id=current_user.tenant_id)
    return MyScoreResponse(
        period=period or f"{hoje:%Y-%m}",
        summary=await service.my_summary(current_user, month),
    )


@taskscore_router.get("/ranking")
async def ranking(
    sort: RankingSort = Query(default="points"),
    period: str | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    clock: Clock = Depends(get_clock),
) -> RankingResponse:
    """Regra 6: ranking completo exige ADMINISTRADOR."""
    hoje = clock.today()
    month = _parse_period(period) if period else hoje.replace(day=1)
    service = TaskscoreService(session=session, tenant_id=current_user.tenant_id)
    return RankingResponse(
        period=period or f"{hoje:%Y-%m}",
        sort=sort,
        items=await service.ranking(sort, month, today=hoje),
    )


@taskscore_router.get("/chart")
async def chart(
    user_id: uuid.UUID | None = Query(default=None),
    granularity: Literal["monthly", "daily"] = Query(default="monthly"),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    clock: Clock = Depends(get_clock),
) -> ScoreChartResponse:
    """Regra 6: gráfico de outro usuário exige ADMINISTRADOR."""
    target = current_user
    if user_id is not None and user_id != current_user.id:
        if current_user.role not in (UserRole.ADMINISTRADOR, UserRole.GESTOR):
            raise HTTPException(status_code=403, detail="Você só pode ver o próprio desempenho.")
        user_service = UserService(session=session, tenant_id=current_user.tenant_id)
        target = await get_or_404(lambda: user_service.get(user_id), "Usuário não encontrado.")
    service = TaskscoreService(session=session, tenant_id=current_user.tenant_id)
    current, previous, goal, days = await service.chart(target, granularity, today=clock.today())
    return ScoreChartResponse(
        granularity=granularity, current=current, previous=previous, goal=goal, days=days
    )
