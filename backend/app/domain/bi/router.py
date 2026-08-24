import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http import parse_month_query
from app.core.permissions import FinancialAccess, UserRole, require_financial, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.bi.schemas import (
    ConversionResponse,
    LostTimeResponse,
    PipelineResponse,
    PortfolioGroupBy,
    PortfolioResponse,
    SuccessRateResponse,
    SuccessTrendResponse,
    TimeFeesByGroupResponse,
    TimeFeesByTypeResponse,
    TimeFeesResponse,
    VintageResponse,
)
from app.domain.bi.service import BiPipelineService, BiTimeFeesService, BiVintageService
from app.domain.lawsuits.models import LawsuitOutcome
from app.domain.users.models import User

router = APIRouter(prefix="/bi", tags=["bi"])


# Regra 9: a aba exige ADMINISTRADOR ou GESTOR — require_role(ADMINISTRADOR) já aceita
# GESTOR pela hierarquia de perfis (spec 005).
@router.get("/pipeline")
async def get_bi_pipeline(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    action_group_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PipelineResponse:
    service = BiPipelineService(session=session, tenant_id=current_user.tenant_id)
    return await service.pipeline(
        from_=from_, to=to, action_group_id=action_group_id, today=date.today()
    )


@router.get("/pipeline/conversion")
async def get_bi_pipeline_conversion(
    period: str | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> ConversionResponse:
    period_start = parse_month_query(period)
    service = BiPipelineService(session=session, tenant_id=current_user.tenant_id)
    return await service.conversion(period=period_start)


@router.get("/pipeline/portfolio")
async def get_bi_pipeline_portfolio(
    group_by: PortfolioGroupBy = Query(default="step"),
    action_group_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PortfolioResponse:
    service = BiPipelineService(session=session, tenant_id=current_user.tenant_id)
    return await service.portfolio(
        group_by=group_by, action_group_id=action_group_id, today=date.today()
    )


# Spec 075 — Safra e Qualidade. Regra 10: exige ADMINISTRADOR ou GESTOR — o mesmo
# require_role(ADMINISTRADOR) das rotas da 074 (GESTOR entra pela hierarquia, spec 005).
@router.get("/vintage")
async def get_bi_vintage(
    from_year: int | None = Query(default=None),
    to_year: int | None = Query(default=None),
    action_group_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> VintageResponse:
    service = BiVintageService(session=session, tenant_id=current_user.tenant_id)
    return await service.vintage(
        from_year=from_year, to_year=to_year, action_group_id=action_group_id
    )


@router.get("/success-rate")
async def get_bi_success_rate(
    period: str | None = Query(default=None),
    action_group_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> SuccessRateResponse:
    period_start = parse_month_query(period)
    service = BiVintageService(session=session, tenant_id=current_user.tenant_id)
    return await service.success_rate(period=period_start, action_group_id=action_group_id)


@router.get("/success-rate/trend")
async def get_bi_success_rate_trend(
    action_group_id: uuid.UUID | None = Query(default=None),
    months: int = Query(default=24, ge=1, le=60),
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> SuccessTrendResponse:
    service = BiVintageService(session=session, tenant_id=current_user.tenant_id)
    return await service.success_trend(
        action_group_id=action_group_id, months=months, today=date.today()
    )


# Spec 076 — Tempo e Honorários. Regra 11: dupla permissão — ADMINISTRADOR ou GESTOR
# (require_role aceita GESTOR pela hierarquia, spec 005) E financial_access ≥ READ_ONLY,
# porque a aba mostra dinheiro. `from`/`to` filtram por data de fechamento (a view só
# tem processos fechados).
@router.get("/time-fees")
async def get_bi_time_fees(
    outcome: LawsuitOutcome | None = Query(default=None),
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    action_group_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    _financial: User = Depends(require_financial(FinancialAccess.READ_ONLY)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> TimeFeesResponse:
    service = BiTimeFeesService(session=session, tenant_id=current_user.tenant_id)
    return await service.time_fees(
        from_=from_, to=to, outcome=outcome, action_group_id=action_group_id
    )


@router.get("/time-fees/by-group")
async def get_bi_time_fees_by_group(
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    _financial: User = Depends(require_financial(FinancialAccess.READ_ONLY)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> TimeFeesByGroupResponse:
    service = BiTimeFeesService(session=session, tenant_id=current_user.tenant_id)
    return await service.cycles_by_group()


@router.get("/time-fees/by-type")
async def get_bi_time_fees_by_type(
    lawsuit_type_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    _financial: User = Depends(require_financial(FinancialAccess.READ_ONLY)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> TimeFeesByTypeResponse:
    service = BiTimeFeesService(session=session, tenant_id=current_user.tenant_id)
    return await service.profitability_by_type(lawsuit_type_id=lawsuit_type_id)


@router.get("/time-fees/lost-time")
async def get_bi_time_fees_lost_time(
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    _financial: User = Depends(require_financial(FinancialAccess.READ_ONLY)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> LostTimeResponse:
    service = BiTimeFeesService(session=session, tenant_id=current_user.tenant_id)
    return await service.lost_time()
