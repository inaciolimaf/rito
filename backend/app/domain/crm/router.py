from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.crm.schemas import (
    BoardCardResponse,
    BoardColumnPageResponse,
    BoardColumnResponse,
    BoardResponse,
)
from app.domain.lawsuits.board_service import BoardService
from app.domain.lawsuits.listing import (
    BOARD_DEFAULT_LIMIT_PER_COLUMN,
    BoardCardRow,
    filters_from_query,
)
from app.domain.lawsuits.schemas import LawsuitFiltersQuery
from app.domain.stages.repository import StepRepository
from app.domain.users.models import User

router = APIRouter(prefix="/crm", tags=["crm"])


def _card_to_response(card: BoardCardRow) -> BoardCardResponse:
    lawsuit = card.lawsuit
    return BoardCardResponse(
        id=lawsuit.id,
        process_number=lawsuit.process_number,
        folder=lawsuit.folder,
        lawsuit_type_name=card.lawsuit_type_name,
        stage_id=lawsuit.stage_id,
        stage_name=card.stage_name,
        case_value=lawsuit.case_value,
        responsible_id=lawsuit.user_id,
        responsible_name=card.responsible_name,
        stage_entered_at=lawsuit.stage_entered_at,
        parties=card.parties,
        parties_total=card.parties_total,
    )


@router.get("/board")
async def get_board(
    filters: LawsuitFiltersQuery = Depends(),
    limit_per_column: int = Query(default=BOARD_DEFAULT_LIMIT_PER_COLUMN, ge=1, le=200),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> BoardResponse:
    """Spec 051, regra 1: as 9 fases, sempre todas, mesmo vazias."""
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
            items=[_card_to_response(card) for card in board.cards_by_step.get(step.id, [])],
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
    service = BoardService(session=session, tenant_id=current_user.tenant_id)
    page = await service.get_board_column(
        filters=filters_from_query(filters), step_id=step_id, cursor=cursor, limit=limit
    )
    return BoardColumnPageResponse(
        items=[_card_to_response(card) for card in page.items],
        next_cursor=page.next_cursor,
        total=page.total,
    )
