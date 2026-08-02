from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.courts.models import CourtSegment
from app.domain.courts.schemas import CourtResponse, CourtSystemResponse
from app.domain.courts.service import CourtService
from app.domain.users.models import User

courts_router = APIRouter(prefix="/courts", tags=["courts"])
court_systems_router = APIRouter(prefix="/court-systems", tags=["courts"])


@courts_router.get("")
async def list_courts(
    q: str | None = Query(default=None),
    segment: CourtSegment | None = Query(default=None),
    state: str | None = Query(default=None, min_length=2, max_length=2),
    _current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> list[CourtResponse]:
    """Regra 1: catálogo é somente leitura pela API — atualização só por migration."""
    courts = await CourtService(session).list_courts(
        query=q, segment=segment, state=state.upper() if state else None
    )
    return [
        CourtResponse(
            id=court.id,
            code=court.code,
            name=court.name,
            segment=court.segment,
            state_code=court.state_code,
            datajud_alias=court.datajud_alias,
            is_active=court.is_active,
        )
        for court in courts
    ]


@court_systems_router.get("")
async def list_court_systems(
    _current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> list[CourtSystemResponse]:
    systems = await CourtService(session).list_systems()
    return [CourtSystemResponse(id=system.id, name=system.name) for system in systems]
