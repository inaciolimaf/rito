from fastapi import APIRouter, Depends, HTTPException, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_redis
from app.core.permissions import FinancialAccess, UserRole, require_role
from app.core.rate_limit import check_and_increment
from app.domain.auth.deps import get_session_for_current_user
from app.domain.crm.schemas import (
    BoardCardResponse,
    BoardColumnPageResponse,
    BoardColumnResponse,
    BoardResponse,
    CrmStatsByStepResponse,
    CrmStatsResponse,
    RecalculateStagnationResponse,
)
from app.domain.lawsuits.board_service import BoardService
from app.domain.lawsuits.listing import (
    BOARD_DEFAULT_LIMIT_PER_COLUMN,
    BoardCardRow,
    filters_from_query,
)
from app.domain.lawsuits.schemas import LawsuitFiltersQuery
from app.domain.lawsuits.stagnation_service import StagnationService
from app.domain.stages.repository import StepRepository
from app.domain.users.models import User

router = APIRouter(prefix="/crm", tags=["crm"])

# Regra 9 (052): recálculo manual limitado a 1x por hora por tenant.
_RECALCULATE_STAGNATION_LIMIT = 1
_RECALCULATE_STAGNATION_WINDOW_SECONDS = 3600


def _card_to_response(card: BoardCardRow, *, can_see_value: bool) -> BoardCardResponse:
    lawsuit = card.lawsuit
    return BoardCardResponse(
        id=lawsuit.id,
        process_number=lawsuit.process_number,
        folder=lawsuit.folder,
        lawsuit_type_name=card.lawsuit_type_name,
        stage_id=lawsuit.stage_id,
        stage_name=card.stage_name,
        # Refatoração 060, Alvo 3: financial_access=NONE não vê valor no card do CRM.
        case_value=lawsuit.case_value if can_see_value else None,
        responsible_id=lawsuit.user_id,
        responsible_name=card.responsible_name,
        stage_entered_at=lawsuit.stage_entered_at,
        parties=card.parties,
        parties_total=card.parties_total,
        is_stagnant=lawsuit.is_stagnant,
        stagnant_since=lawsuit.stagnant_since,
        stagnant_days=card.stagnant_days,
    )


@router.get("/board")
async def get_board(
    filters: LawsuitFiltersQuery = Depends(),
    limit_per_column: int = Query(default=BOARD_DEFAULT_LIMIT_PER_COLUMN, ge=1, le=200),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> BoardResponse:
    """Spec 051, regra 1: as 9 fases, sempre todas, mesmo vazias."""
    can_see_value = current_user.financial_access != FinancialAccess.NONE
    steps = await StepRepository(session).list_all()
    service = BoardService(session=session, tenant_id=current_user.tenant_id)
    board = await service.get_board(
        filters=filters_from_query(filters), limit_per_column=limit_per_column
    )
    columns = [
        BoardColumnResponse(
            step_id=step.id,
            step_name=step.name,
            total=board.counts_by_step.get(step.id, 0),
            items=[
                _card_to_response(card, can_see_value=can_see_value)
                for card in board.cards_by_step.get(step.id, [])
            ],
        )
        for step in steps
    ]
    return BoardResponse(
        columns=columns, total=board.total, suggest_refine_filters=board.suggest_refine
    )


@router.get("/board/column/{step_id}")
async def get_board_column(
    step_id: int,
    filters: LawsuitFiltersQuery = Depends(),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=BOARD_DEFAULT_LIMIT_PER_COLUMN, ge=1, le=200),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> BoardColumnPageResponse:
    """Spec 051, regra 7: paginação por scroll de UMA coluna."""
    can_see_value = current_user.financial_access != FinancialAccess.NONE
    service = BoardService(session=session, tenant_id=current_user.tenant_id)
    page = await service.get_board_column(
        filters=filters_from_query(filters), step_id=step_id, cursor=cursor, limit=limit
    )
    return BoardColumnPageResponse(
        items=[_card_to_response(card, can_see_value=can_see_value) for card in page.items],
        next_cursor=page.next_cursor,
        total=page.total,
    )


@router.get("/stats")
async def get_stats(
    filters: LawsuitFiltersQuery = Depends(),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> CrmStatsResponse:
    """§5: cards de topo do CRM — mesmos filtros do board (regra 8, spec 051)."""
    can_see_value = current_user.financial_access != FinancialAccess.NONE
    steps = await StepRepository(session).list_all()
    service = BoardService(session=session, tenant_id=current_user.tenant_id)
    stats = await service.get_stats(filters=filters_from_query(filters))
    by_step = {row.step_id: row for row in stats.by_step}
    return CrmStatsResponse(
        total_lawsuits=stats.total_lawsuits,
        received_this_month=stats.received_this_month,
        # Refatoração 060, Alvo 3: financial_access=NONE não vê valor no CRM.
        total_value=stats.total_value if can_see_value else None,
        stagnant_count=stats.stagnant_count,
        stagnant_value=stats.stagnant_value if can_see_value else None,
        by_step=[
            CrmStatsByStepResponse(
                step_id=step.id,
                step_name=step.name,
                total=by_step[step.id].total if step.id in by_step else 0,
                stagnant_count=by_step[step.id].stagnant_count if step.id in by_step else 0,
            )
            for step in steps
        ],
    )


@router.post("/recalculate-stagnation")
async def recalculate_stagnation(
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    redis: Redis = Depends(get_redis),
) -> RecalculateStagnationResponse:
    """Regra 9: 1x por hora por tenant — o job diário (regra 4) é quem cobre o resto."""
    allowed = await check_and_increment(
        redis,
        f"stagnation_recalc:{current_user.tenant_id}",
        limit=_RECALCULATE_STAGNATION_LIMIT,
        window_seconds=_RECALCULATE_STAGNATION_WINDOW_SECONDS,
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="Recálculo manual já foi feito na última hora.")
    service = StagnationService(session=session, tenant_id=current_user.tenant_id)
    recalculated = await service.recalculate_tenant()
    return RecalculateStagnationResponse(recalculated_count=recalculated)
