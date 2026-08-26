"""Rotas da IA no editor (spec 088 §5).

Três delas respondem em SSE (continuar, reescrever, tom): é texto que a pessoa lê
enquanto aparece. As outras duas respondem JSON porque a saída é estruturada — checklist
de revisão e fundamentação já passada pelo guarda-corpo de citação.
"""

import json
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import UserRole, require_role
from app.domain.ai.editor import (
    MAX_SELECTION,
    TONE_INSTRUCTIONS,
    ActionNotFoundError,
    EditorAiService,
    SelectionTooLongError,
)
from app.domain.ai.exceptions import FeatureDisabledError
from app.domain.ai.router import get_llm_provider
from app.domain.ai.service import AiRunner
from app.domain.ai.sse import SSE_MEDIA_TYPE
from app.domain.auth.deps import get_session_for_current_user
from app.domain.users.models import User
from app.integrations.openrouter.types import LLMChunk, LLMNotConfiguredError, LLMProvider

router = APIRouter(prefix="/ai/editor", tags=["ai"])

_UNAVAILABLE = "A assistência de escrita não está disponível neste escritório."
_TOO_LONG = (
    f"Seleção muito grande (máximo {MAX_SELECTION} caracteres). "
    "Selecione um trecho menor — o resultado também fica melhor."
)


class ContinueRequest(BaseModel):
    context_before: str = Field(min_length=1)
    context_after: str = ""
    template_id: uuid.UUID | None = None
    lawsuit_id: uuid.UUID | None = None


class RewriteRequest(BaseModel):
    selection: str = Field(min_length=1)
    instruction: str = Field(min_length=1, max_length=500)
    template_id: uuid.UUID | None = None


class ToneRequest(BaseModel):
    selection: str = Field(min_length=1)
    tone: Literal["formal", "objetivo", "tecnico", "simples"]
    template_id: uuid.UUID | None = None


class ReviewRequest(BaseModel):
    template_id: uuid.UUID
    lawsuit_id: uuid.UUID | None = None


class GroundRequest(BaseModel):
    selection: str = Field(min_length=1)
    lawsuit_id: uuid.UUID
    template_id: uuid.UUID | None = None


class FeedbackRequest(BaseModel):
    accepted: bool


class ReviewItemResponse(BaseModel):
    topic: str
    label: str
    status: str
    note: str


class ReviewResponse(BaseModel):
    action_id: uuid.UUID
    items: list[ReviewItemResponse]
    # Regra 6: o documento não foi tocado — a UI diz isso em voz alta.
    document_changed: bool = False


class GroundResponse(BaseModel):
    action_id: uuid.UUID
    output: str
    warnings: list[dict[str, str]]


class FeedbackResponse(BaseModel):
    id: uuid.UUID
    accepted: bool | None
    created_at: datetime


def _service(session: AsyncSession, user: User, provider: LLMProvider) -> EditorAiService:
    return EditorAiService(
        session=session,
        tenant_id=user.tenant_id,
        runner=AiRunner(session, user.tenant_id, provider),
    )


def _sse(chunks: Any) -> StreamingResponse:
    async def generate() -> Any:
        try:
            async for chunk in chunks:
                yield _format(chunk)
        except (LLMNotConfiguredError, FeatureDisabledError):
            # Regra 11: sem IA, o cliente recebe um evento de erro claro e esconde o
            # menu — a rota não explode no meio do stream.
            yield _format(LLMChunk(kind="error", error=_UNAVAILABLE))

    return StreamingResponse(generate(), media_type=SSE_MEDIA_TYPE)


def _format(chunk: LLMChunk) -> str:
    payload: dict[str, Any] = {}
    if chunk.kind == "chunk":
        payload = {"content": chunk.content or ""}
    elif chunk.kind == "done":
        # `finish_reason` carrega o id da ação: é com ele que o editor manda o feedback.
        payload = {"action_id": chunk.finish_reason}
    elif chunk.kind == "error":
        payload = {"message": chunk.error or _UNAVAILABLE}
    return f"event: {chunk.kind}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/continue")
async def continue_writing(
    payload: ContinueRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> StreamingResponse:
    service = _service(session, current_user, provider)
    return _sse(
        service.continue_text(
            user=current_user,
            template_id=payload.template_id,
            context_before=payload.context_before,
            context_after=payload.context_after,
        )
    )


@router.post("/rewrite")
async def rewrite_selection(
    payload: RewriteRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> StreamingResponse:
    service = _service(session, current_user, provider)
    if len(payload.selection) > MAX_SELECTION:
        raise HTTPException(status_code=422, detail=_TOO_LONG)
    return _sse(
        service.rewrite(
            user=current_user,
            template_id=payload.template_id,
            selection=payload.selection,
            instruction=payload.instruction,
        )
    )


@router.post("/tone")
async def adjust_tone(
    payload: ToneRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> StreamingResponse:
    service = _service(session, current_user, provider)
    if len(payload.selection) > MAX_SELECTION:
        raise HTTPException(status_code=422, detail=_TOO_LONG)
    assert payload.tone in TONE_INSTRUCTIONS
    return _sse(
        service.tone(
            user=current_user,
            template_id=payload.template_id,
            selection=payload.selection,
            tone=payload.tone,
        )
    )


@router.post("/review")
async def review_document(
    payload: ReviewRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> ReviewResponse:
    """Regra 6: aponta, não corrige — a resposta não tem texto para aplicar."""
    service = _service(session, current_user, provider)
    try:
        action, items = await service.review(
            user=current_user, template_id=payload.template_id, lawsuit_id=payload.lawsuit_id
        )
    except ActionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Modelo não encontrado.") from exc
    except (LLMNotConfiguredError, FeatureDisabledError) as exc:
        raise HTTPException(status_code=409, detail=_UNAVAILABLE) from exc
    return ReviewResponse(
        action_id=action.id,
        items=[ReviewItemResponse(**item.__dict__) for item in items],
    )


@router.post("/ground")
async def suggest_grounding(
    payload: GroundRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> GroundResponse:
    service = _service(session, current_user, provider)
    try:
        result = await service.ground(
            user=current_user,
            template_id=payload.template_id,
            selection=payload.selection,
            lawsuit_id=payload.lawsuit_id,
        )
    except SelectionTooLongError as exc:
        raise HTTPException(status_code=422, detail=_TOO_LONG) from exc
    except (LLMNotConfiguredError, FeatureDisabledError) as exc:
        raise HTTPException(status_code=409, detail=_UNAVAILABLE) from exc
    return GroundResponse(
        action_id=result.action.id, output=result.output, warnings=result.warnings
    )


@router.post("/actions/{action_id}/feedback")
async def send_feedback(
    action_id: uuid.UUID,
    payload: FeedbackRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> FeedbackResponse:
    service = _service(session, current_user, provider)
    try:
        action = await service.feedback(action_id, accepted=payload.accepted)
    except ActionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Ação de IA não encontrada.") from exc
    return FeedbackResponse(id=action.id, accepted=action.accepted, created_at=action.created_at)
