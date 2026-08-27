"""Rotas da busca global (spec 096 §5)."""

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.search.service import MAX_PER_FACET, FacetResult, SearchService
from app.domain.users.models import User

router = APIRouter(prefix="/search", tags=["search"])


class SearchHitResponse(BaseModel):
    id: uuid.UUID
    label: str
    sublabel: str | None
    extra: dict[str, str]


class FacetResponse(BaseModel):
    items: list[SearchHitResponse]
    total: int


class SearchResponse(BaseModel):
    people: FacetResponse
    lawsuits: FacetResponse
    tasks: FacetResponse
    # Regra 11: volta na resposta para dar como monitorar a meta de 200 ms sem depender
    # de instrumentação externa.
    took_ms: int
    query_kind: str
    recent: list[str] = Field(default_factory=list)


class RecentResponse(BaseModel):
    items: list[str]


class ClickRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    type: str | None = None
    id: uuid.UUID | None = None


def _to_facet(resultado: FacetResult) -> FacetResponse:
    return FacetResponse(
        items=[
            SearchHitResponse(
                id=item.id,
                label=item.label,
                sublabel=item.sublabel,
                extra={chave: str(valor) for chave, valor in item.extra.items()},
            )
            for item in resultado.items
        ],
        total=resultado.total,
    )


@router.get("")
async def search(
    q: str = Query(default=""),
    facet: str = Query(default="all", pattern="^(all|people|lawsuits)$"),
    limit: int = Query(default=MAX_PER_FACET, ge=1, le=MAX_PER_FACET),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> SearchResponse:
    service = SearchService(session, current_user.tenant_id)
    resultados = await service.search(q, user=current_user, facet=facet, limit=limit)
    return SearchResponse(
        people=_to_facet(resultados.people),
        lawsuits=_to_facet(resultados.lawsuits),
        tasks=_to_facet(resultados.tasks),
        took_ms=resultados.took_ms,
        query_kind=resultados.parsed_kind,
        recent=resultados.recent,
    )


@router.get("/recent")
async def recent_searches(
    limit: int = Query(default=5, ge=1, le=20),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> RecentResponse:
    service = SearchService(session, current_user.tenant_id)
    return RecentResponse(items=await service.recent(user_id=current_user.id, limit=limit))


@router.post("/click", status_code=204)
async def record_click(
    payload: ClickRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    service = SearchService(session, current_user.tenant_id)
    await service.record_click(
        user_id=current_user.id,
        query=payload.query,
        clicked_type=payload.type,
        clicked_id=payload.id,
    )
