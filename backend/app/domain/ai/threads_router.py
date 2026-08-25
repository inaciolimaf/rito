"""Rotas de thread de agente (spec 082 §6).

Router só faz HTTP: monta o service, traduz exceção em status e serializa. Toda regra
(de quem é o thread, o que pode ser retomado, o que o grafo faz) mora no service e no
runtime.
"""

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.graphs.base import GraphDeps, GraphResult
from app.ai.graphs.registry import UnknownGraphError
from app.ai.runtime import GraphRuntime, StepEvent
from app.core.permissions import UserRole, require_role
from app.domain.ai.models import AiStep, AiThread
from app.domain.ai.router import get_llm_provider
from app.domain.ai.schemas import (
    PendingActionResponse,
    StepListResponse,
    StepResponse,
    ThreadCreateRequest,
    ThreadListResponse,
    ThreadResponse,
    ThreadResumeRequest,
)
from app.domain.ai.service import AiRunner
from app.domain.ai.sse import SSE_MEDIA_TYPE
from app.domain.ai.threads import (
    AiThreadService,
    ThreadForbiddenError,
    ThreadNotResumableError,
)
from app.domain.auth.deps import get_session_for_current_user
from app.domain.users.models import User
from app.integrations.openrouter.types import LLMProvider

router = APIRouter(prefix="/ai/threads", tags=["ai"])

_FORBIDDEN_DETAIL = "Esta conversa é de outro usuário."
_DEFAULT_PAGE_SIZE = 20


def _to_thread_response(thread: AiThread) -> ThreadResponse:
    pending = thread.pending_action
    return ThreadResponse(
        id=thread.id,
        graph_name=thread.graph_name,
        feature_key=thread.feature_key,
        title=thread.title,
        status=thread.status,
        context=thread.context or {},
        pending_action=PendingActionResponse(**pending) if pending else None,
        output=thread.output,
        error=thread.error,
        step_count=thread.step_count,
        user_id=thread.user_id,
        waiting_since=thread.waiting_since,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


def _to_step_response(step: AiStep) -> StepResponse:
    return StepResponse(
        id=step.id,
        step=step.step,
        node=step.node,
        kind=step.kind,
        input=step.input,
        output=step.output,
        duration_ms=step.duration_ms,
        error=step.error,
        created_at=step.created_at,
    )


def _build_service(
    session: AsyncSession, user: User, provider: LLMProvider, thread: AiThread | None = None
) -> AiThreadService:
    """O runtime recebe o `AiRunner` da 081 como dependência do grafo — nenhum nó
    escolhe modelo nem conta token por conta própria."""
    service = AiThreadService(session=session, tenant_id=user.tenant_id)
    if thread is not None:
        service.runtime = GraphRuntime(
            session,
            user.tenant_id,
            deps=GraphDeps(
                tenant_id=user.tenant_id,
                user_id=user.id,
                llm=AiRunner(session, user.tenant_id, provider),
                feature_key=thread.feature_key,
                context=dict(thread.context or {}),
            ),
        )
    return service


@router.post("", status_code=201)
async def create_thread(
    payload: ThreadCreateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> ThreadResponse:
    service = _build_service(session, current_user, provider)
    try:
        thread = await service.create(
            user=current_user,
            graph_name=payload.graph_name,
            title=payload.title,
            context=payload.context,
        )
    except UnknownGraphError as exc:
        raise HTTPException(status_code=422, detail="Agente desconhecido.") from exc
    if payload.autorun:
        runner = _build_service(session, current_user, provider, thread)
        await runner.run(thread, payload.input)
    else:
        # Sem autorun o input fica guardado para o SSE executar depois.
        thread.state = {"input": payload.input, "scratch": {}, "messages": []}
    return _to_thread_response(thread)


@router.get("")
async def list_threads(
    cursor: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=100),
    all_users: bool = Query(default=False, alias="all"),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> ThreadListResponse:
    """`all=true` é a visão de auditoria (regra 11): só ADMINISTRADOR e acima."""
    service = _build_service(session, current_user, provider)
    is_auditor = current_user.role in (UserRole.ADMINISTRADOR, UserRole.GESTOR)
    if all_users and not is_auditor:
        raise HTTPException(status_code=403, detail="Exige perfil ADMINISTRADOR ou superior.")
    rows, total = await service.threads.list_for_user(
        user_id=None if all_users else current_user.id, cursor=cursor, limit=limit
    )
    return ThreadListResponse(
        items=[_to_thread_response(row) for row in rows],
        next_cursor=str(rows[-1].id) if len(rows) == limit else None,
        total=total,
    )


@router.get("/{thread_id}")
async def get_thread(
    thread_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> ThreadResponse:
    service = _build_service(session, current_user, provider)
    try:
        thread = await service.get_for(thread_id, current_user)
    except ThreadForbiddenError as exc:
        raise HTTPException(status_code=403, detail=_FORBIDDEN_DETAIL) from exc
    return _to_thread_response(thread)


@router.post("/{thread_id}/resume")
async def resume_thread(
    thread_id: uuid.UUID,
    payload: ThreadResumeRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> ThreadResponse:
    service = _build_service(session, current_user, provider)
    try:
        thread = await service.get_for(thread_id, current_user)
        service = _build_service(session, current_user, provider, thread)
        await service.resume(
            thread,
            user=current_user,
            approved=payload.approved,
            human_input=payload.human_input,
        )
    except ThreadForbiddenError as exc:
        raise HTTPException(status_code=403, detail=_FORBIDDEN_DETAIL) from exc
    except ThreadNotResumableError as exc:
        raise HTTPException(
            status_code=409, detail="Esta conversa não está aguardando confirmação."
        ) from exc
    return _to_thread_response(thread)


@router.post("/{thread_id}/cancel")
async def cancel_thread(
    thread_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> ThreadResponse:
    service = _build_service(session, current_user, provider)
    try:
        thread = await service.get_for(thread_id, current_user)
        await service.cancel(thread, current_user)
    except ThreadForbiddenError as exc:
        raise HTTPException(status_code=403, detail=_FORBIDDEN_DETAIL) from exc
    return _to_thread_response(thread)


@router.get("/{thread_id}/steps")
async def list_thread_steps(
    thread_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> StepListResponse:
    service = _build_service(session, current_user, provider)
    try:
        thread = await service.get_for(thread_id, current_user)
    except ThreadForbiddenError as exc:
        raise HTTPException(status_code=403, detail=_FORBIDDEN_DETAIL) from exc
    steps = list(await service.list_steps(thread))
    return StepListResponse(items=[_to_step_response(step) for step in steps], total=len(steps))


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


@router.get("/{thread_id}/stream")
async def stream_thread(
    thread_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> StreamingResponse:
    """SSE dos passos (regra 7). Thread ainda parado (`pending`) executa agora e o
    cliente assiste do primeiro passo; thread que já rodou tem os passos reemitidos —
    reconectar não perde o histórico."""
    service = _build_service(session, current_user, provider)
    try:
        thread = await service.get_for(thread_id, current_user)
    except ThreadForbiddenError as exc:
        raise HTTPException(status_code=403, detail=_FORBIDDEN_DETAIL) from exc
    service = _build_service(session, current_user, provider, thread)

    async def generate() -> Any:
        if thread.status == "pending":
            async for event in service.stream(thread, None):
                if isinstance(event, StepEvent):
                    yield _sse(
                        "step",
                        {
                            "step": event.step,
                            "node": event.node,
                            "kind": event.kind,
                            "output": event.output,
                            "duration_ms": event.duration_ms,
                        },
                    )
                elif isinstance(event, GraphResult):
                    yield _sse(_result_event(event), _result_payload(event))
            return
        for step in await service.list_steps(thread):
            yield _sse(
                "step",
                {
                    "step": step.step,
                    "node": step.node,
                    "kind": step.kind,
                    "output": step.output,
                    "duration_ms": step.duration_ms,
                },
            )
        yield _sse(
            "done" if thread.status == "done" else thread.status,
            {"status": thread.status, "output": thread.output, "error": thread.error},
        )

    return StreamingResponse(generate(), media_type=SSE_MEDIA_TYPE)


def _result_event(result: GraphResult) -> str:
    return {"waiting_human": "interrupt", "error": "error"}.get(result.status, "done")


def _result_payload(result: GraphResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "output": result.output,
        "pending_action": result.pending_action,
        "error": result.error,
    }
