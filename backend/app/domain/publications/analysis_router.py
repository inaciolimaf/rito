"""Rotas da análise de intimação (spec 086 §5)."""

import uuid
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http import get_or_404
from app.core.permissions import UserRole, require_role
from app.domain.ai.exceptions import FeatureDisabledError
from app.domain.ai.router import get_llm_provider
from app.domain.ai.service import AiRunner
from app.domain.auth.deps import get_session_for_current_user
from app.domain.publications.analysis import AnalysisNotFoundError, PublicationAnalysisService
from app.domain.publications.analysis_models import PublicationAnalysis
from app.domain.publications.deadline import should_prefill
from app.domain.publications.service import PublicationService
from app.domain.users.models import User
from app.integrations.openrouter.types import LLMError, LLMNotConfiguredError, LLMProvider

router = APIRouter(prefix="/publications", tags=["publications"])

_NOT_FOUND = "Intimação não encontrada."


class AnalysisResponse(BaseModel):
    id: uuid.UUID
    publication_id: uuid.UUID
    summary: str
    act_type: str | None
    requires_action: bool
    deadline_days: int | None
    deadline_kind: str | None
    deadline_date: date | None
    deadline_confidence: float | None
    # Regra 4: a UI usa isto para decidir se pré-preenche o campo de prazo.
    should_prefill_deadline: bool
    suggested_task_type_id: uuid.UUID | None
    suggested_user_id: uuid.UUID | None
    reasoning: str | None
    model: str
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    human_correction: dict[str, Any] | None
    created_at: datetime


class ReviewRequest(BaseModel):
    approved: bool = True
    deadline_date: date | None = None
    task_type_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None


class ReviewResponse(BaseModel):
    analysis: AnalysisResponse
    # Nulo quando a revisão não gerou tarefa (intimação sem processo, ou recusada).
    post_id: uuid.UUID | None


class EstimateResponse(BaseModel):
    count: int
    estimated_prompt_tokens: int
    note: str


def _to_response(analysis: PublicationAnalysis) -> AnalysisResponse:
    confianca = (
        float(analysis.deadline_confidence) if analysis.deadline_confidence is not None else None
    )
    return AnalysisResponse(
        id=analysis.id,
        publication_id=analysis.publication_id,
        summary=analysis.summary,
        act_type=analysis.act_type,
        requires_action=analysis.requires_action,
        deadline_days=analysis.deadline_days,
        deadline_kind=analysis.deadline_kind,
        deadline_date=analysis.deadline_date,
        deadline_confidence=confianca,
        should_prefill_deadline=should_prefill(confianca) and analysis.deadline_date is not None,
        suggested_task_type_id=analysis.suggested_task_type_id,
        suggested_user_id=analysis.suggested_user_id,
        reasoning=analysis.reasoning,
        model=analysis.model,
        reviewed_by=analysis.reviewed_by,
        reviewed_at=analysis.reviewed_at,
        human_correction=analysis.human_correction,
        created_at=analysis.created_at,
    )


def _service(
    session: AsyncSession, user: User, provider: LLMProvider
) -> PublicationAnalysisService:
    return PublicationAnalysisService(
        session=session,
        tenant_id=user.tenant_id,
        runner=AiRunner(session, user.tenant_id, provider),
    )


@router.post("/{publication_id}/analyze")
async def analyze_publication(
    publication_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> AnalysisResponse:
    publications = PublicationService(session=session, tenant_id=current_user.tenant_id)
    publication = await get_or_404(lambda: publications.get_by_id(publication_id), _NOT_FOUND)
    service = _service(session, current_user, provider)
    try:
        analysis = await service.analyze(publication, user=current_user)
    except (LLMNotConfiguredError, FeatureDisabledError) as exc:
        raise HTTPException(
            status_code=409, detail="A análise por IA não está disponível neste escritório."
        ) from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"O modelo não respondeu: {exc}") from exc
    return _to_response(analysis)


@router.get("/{publication_id}/analysis")
async def get_analysis(
    publication_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> AnalysisResponse:
    service = _service(session, current_user, provider)
    analysis = await get_or_404(
        lambda: service.analyses.get_for_publication(publication_id),
        "Esta intimação ainda não foi analisada.",
    )
    return _to_response(analysis)


@router.post("/{publication_id}/analysis/review")
async def review_analysis(
    publication_id: uuid.UUID,
    payload: ReviewRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> ReviewResponse:
    """Regra 1: o prazo vira prazo aqui — com nome e hora de quem confirmou."""
    publications = PublicationService(session=session, tenant_id=current_user.tenant_id)
    publication = await get_or_404(lambda: publications.get_by_id(publication_id), _NOT_FOUND)
    service = _service(session, current_user, provider)
    try:
        analysis, post_id = await service.review(
            publication,
            user=current_user,
            approved=payload.approved,
            deadline_date=payload.deadline_date,
            task_type_id=payload.task_type_id,
            user_id=payload.user_id,
        )
    except AnalysisNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Esta intimação ainda não foi analisada."
        ) from exc
    return ReviewResponse(analysis=_to_response(analysis), post_id=post_id)


@router.get("/analysis/estimate")
async def estimate_analysis(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> EstimateResponse:
    """Regra 12: "analisar todas" mostra o tamanho da conta antes de gastar."""
    service = _service(session, current_user, provider)
    pendentes = await service.analyses.publications_without_analysis(limit)
    return EstimateResponse(**await service.estimate_cost(pendentes))
