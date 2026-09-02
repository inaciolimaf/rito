from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.locations.schemas import CityResponse, StateResponse
from app.domain.locations.service import LocationService
from app.domain.users.models import User

states_router = APIRouter(prefix="/states", tags=["locations"])
cities_router = APIRouter(prefix="/cities", tags=["locations"])


@states_router.get("")
async def list_states(
    _current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> list[StateResponse]:
    states = await LocationService(session).list_states()
    return [StateResponse(code=s.code, name=s.name, ibge_code=s.ibge_code) for s in states]


@cities_router.get("")
async def list_cities(
    state: str = Query(..., min_length=2, max_length=2),
    q: str | None = Query(default=None),
    _current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> list[CityResponse]:
    cities = await LocationService(session).list_cities(state_code=state, query=q)
    return [
        CityResponse(ibge_code=c.ibge_code, name=c.name, state_code=c.state_code) for c in cities
    ]
