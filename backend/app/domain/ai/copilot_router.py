"""Rotas do copiloto (spec 085 §5).

Duas portas para o mesmo turno: `POST /message` responde em JSON (útil para script e
para teste) e `GET /stream` responde em SSE (o que o painel usa, regra 2). As duas
passam pelo mesmo `CopilotService` — não há caminho em que a conversa siga regras
diferentes por causa do transporte.
"""

import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.runtime import RuntimeSessionLostError
from app.core.permissions import UserRole, require_role
from app.domain.ai.copilot import (
    MAX_MESSAGES_PER_THREAD,
    CopilotService,
    CopilotUnavailableError,
    ThreadLimitReachedError,
)
from app.domain.ai.models import AiMessage, AiThread
from app.domain.ai.router import get_llm_provider
from app.domain.ai.sse import SSE_MEDIA_TYPE
from app.domain.ai.threads import ThreadForbiddenError
from app.domain.auth.deps import get_session_for_current_user
from app.domain.users.models import User
from app.integrations.openrouter.types import LLMProvider

router = APIRouter(prefix="/ai/copilot", tags=["ai"])

_FORBIDDEN = "Esta conversa é de outro usuário."
_LIMIT_DETAIL = (
    f"Esta conversa chegou a {MAX_MESSAGES_PER_THREAD} mensagens. "
    "Comece uma nova para o assistente continuar com contexto limpo."
)
# Spec 103: a conversa já registrou o erro; o que não sobreviveu foi a transação.
_SESSION_LOST_DETAIL = (
    "O assistente foi interrompido por tempo esgotado e esta requisição não pôde "
    "continuar. O erro ficou registrado na conversa."
)


class MessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    thread_id: uuid.UUID | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    # Regra 9: o usuário pode trocar o modelo no próprio painel.
    model: str | None = None


class MessageResponse(BaseModel):
    thread_id: uuid.UUID
    title: str | None
    status: str
    reply: str | None
    pending_action: dict[str, Any] | None
    tool_labels: list[str]
    model: str | None


class ThreadSummaryResponse(BaseModel):
    id: uuid.UUID
    title: str | None
    status: str
    model: str | None
    archived_at: datetime | None
    updated_at: datetime
    created_at: datetime


class ThreadListResponse(BaseModel):
    items: list[ThreadSummaryResponse]
    total: int


class MessageItemResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str | None
    action_id: uuid.UUID | None
    created_at: datetime


class ThreadDetailResponse(BaseModel):
    thread: ThreadSummaryResponse
    items: list[MessageItemResponse]


class SuggestionsResponse(BaseModel):
    items: list[str]


def _service(
    session: AsyncSession,
    user: User,
    provider: LLMProvider,
    request: Request | None = None,
) -> CopilotService:
    """`request` só é passado por quem EXECUTA um turno: é dele que sai a fábrica de
    sessão que cria a conversa nova de forma durável (spec 103). Listar, ler e apagar
    não criam nada e não precisam."""
    return CopilotService(
        session=session,
        tenant_id=user.tenant_id,
        provider=provider,
        thread_sessions=None if request is None else request.app.state.session_factory,
    )


def _to_thread(thread: AiThread) -> ThreadSummaryResponse:
    return ThreadSummaryResponse(
        id=thread.id,
        title=thread.title,
        status=thread.status,
        model=thread.model,
        archived_at=thread.archived_at,
        updated_at=thread.updated_at,
        created_at=thread.created_at,
    )


def _to_message(message: AiMessage) -> MessageItemResponse:
    return MessageItemResponse(
        id=message.id,
        role=message.role,
        content=message.content,
        action_id=message.action_id,
        created_at=message.created_at,
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _unavailable(exc: Exception) -> HTTPException:
    """Regra 10: 409 com o motivo — a UI usa isso para esconder o painel, não para
    mostrar erro vermelho."""
    return HTTPException(status_code=409, detail=str(exc))


@router.get("/suggestions")
async def get_suggestions(
    route: str | None = Query(default=None, alias="context"),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> SuggestionsResponse:
    """Regra 5: a sugestão útil depende da tela."""
    service = _service(session, current_user, provider)
    return SuggestionsResponse(items=service.suggestions(route))


@router.get("/threads")
async def list_threads(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> ThreadListResponse:
    service = _service(session, current_user, provider)
    rows, total = await service.threads.threads.list_for_user(
        user_id=current_user.id, cursor=None, limit=limit
    )
    conversas = [thread for thread in rows if thread.graph_name == "base_agent"]
    return ThreadListResponse(
        items=[_to_thread(thread) for thread in conversas], total=len(conversas)
    )


@router.get("/threads/{thread_id}")
async def get_thread(
    thread_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> ThreadDetailResponse:
    service = _service(session, current_user, provider)
    try:
        thread = await service.threads.get_for(thread_id, current_user)
    except ThreadForbiddenError as exc:
        raise HTTPException(status_code=403, detail=_FORBIDDEN) from exc
    mensagens = await service.list_messages(thread)
    return ThreadDetailResponse(
        thread=_to_thread(thread), items=[_to_message(item) for item in mensagens]
    )


@router.delete("/threads/{thread_id}", status_code=204)
async def delete_thread(
    thread_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> None:
    service = _service(session, current_user, provider)
    try:
        thread = await service.threads.get_for(thread_id, current_user)
        await service.delete_thread(thread, current_user)
    except ThreadForbiddenError as exc:
        raise HTTPException(status_code=403, detail=_FORBIDDEN) from exc


@router.post("/message")
async def send_message(
    payload: MessageRequest,
    request: Request,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> MessageResponse:
    service = _service(session, current_user, provider, request)
    try:
        thread, state = await service.start_turn(
            user=current_user,
            thread_id=payload.thread_id,
            message=payload.message,
            context=payload.context,
            model=payload.model,
        )
    except CopilotUnavailableError as exc:
        raise _unavailable(exc) from exc
    except ThreadForbiddenError as exc:
        raise HTTPException(status_code=403, detail=_FORBIDDEN) from exc
    except ThreadLimitReachedError as exc:
        raise HTTPException(status_code=409, detail=_LIMIT_DETAIL) from exc

    try:
        turn = await service.run_turn(user=current_user, thread=thread, state=state)
    except RuntimeSessionLostError as exc:
        raise HTTPException(status_code=503, detail=_SESSION_LOST_DETAIL) from exc
    return MessageResponse(
        thread_id=thread.id,
        title=thread.title,
        status=thread.status,
        reply=turn.reply,
        pending_action=turn.pending_action,
        tool_labels=turn.tool_labels,
        model=thread.model,
    )


async def _turn_events(
    service: Any,
    current_user: User,
    thread: Any,
    state: Any,
    session: AsyncSession,
) -> AsyncIterator[str]:
    """Os eventos SSE de um turno do copiloto.

    Perder a sessão no meio (spec 103) não pode virar 503: a resposta já começou e o
    status HTTP já foi enviado. O turno termina como `error` no próprio fluxo, e o
    rollback devolve a conexão ao pool — quem abriu a transação está esperando por ele.
    """
    try:
        async for event, data in service.stream_turn(user=current_user, thread=thread, state=state):
            yield _sse(event, data)
    except RuntimeSessionLostError:
        yield _sse("error", {"message": _SESSION_LOST_DETAIL})
        yield _sse("done", {"thread_id": str(thread.id), "status": "error"})
        await session.rollback()


@router.get("/stream/{thread_id}")
async def stream_message(
    thread_id: uuid.UUID,
    message: str = Query(min_length=1, max_length=4000),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> StreamingResponse:
    """SSE do turno (regras 2 e 3): `tool` enquanto o agente consulta, `message` com a
    resposta, `action` quando algo espera confirmação, `done` no fim."""
    service = _service(session, current_user, provider)
    try:
        thread, state = await service.start_turn(
            user=current_user, thread_id=thread_id, message=message, context=None
        )
    except CopilotUnavailableError as exc:
        raise _unavailable(exc) from exc
    except ThreadForbiddenError as exc:
        raise HTTPException(status_code=403, detail=_FORBIDDEN) from exc
    except ThreadLimitReachedError as exc:
        raise HTTPException(status_code=409, detail=_LIMIT_DETAIL) from exc

    corpo = _turn_events(service, current_user, thread, state, session)
    return StreamingResponse(corpo, media_type=SSE_MEDIA_TYPE)
