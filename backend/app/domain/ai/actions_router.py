"""Rotas das ações de escrita da IA (spec 084 §6).

Aprovar e rejeitar são as duas rotas mais sensíveis da fase de IA: é aqui que uma
proposta vira gravação. Por isso o router não decide nada — ele identifica quem está
pedindo e delega ao `AiActionService`, que carrega as regras.
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http import get_or_404
from app.core.permissions import UserRole, require_role
from app.domain.ai.actions import (
    ActionForbiddenError,
    ActionNotPendingError,
    AiActionService,
    UndoNotAllowedError,
)
from app.domain.ai.models import AiAction, AiAuditLog
from app.domain.ai.service import AiConfigService
from app.domain.auth.deps import get_session_for_current_user
from app.domain.users.models import User

router = APIRouter(prefix="/ai", tags=["ai"])

_NOT_FOUND = "Ação de IA não encontrada."
_FORBIDDEN = "Só quem pediu a ação pode decidir sobre ela."


class ActionResponse(BaseModel):
    id: uuid.UUID
    thread_id: uuid.UUID | None
    tool_name: str
    status: str
    preview: dict[str, Any]
    before_state: dict[str, Any] | None
    affected_type: str | None
    affected_id: uuid.UUID | None
    rejection_reason: str | None
    error: str | None
    expires_at: datetime
    executed_at: datetime | None
    undone_at: datetime | None
    created_at: datetime


class ActionListResponse(BaseModel):
    items: list[ActionResponse]
    total: int


class RejectRequest(BaseModel):
    reason: str | None = None


class AuditEntryResponse(BaseModel):
    id: uuid.UUID
    action_id: uuid.UUID
    tool_name: str
    affected_type: str
    affected_id: uuid.UUID
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    model: str
    thread_id: uuid.UUID | None
    user_id: uuid.UUID
    created_at: datetime


class AuditListResponse(BaseModel):
    items: list[AuditEntryResponse]
    total: int


def _to_action(action: AiAction) -> ActionResponse:
    return ActionResponse(
        id=action.id,
        thread_id=action.thread_id,
        tool_name=action.tool_name,
        status=action.status,
        preview=action.preview,
        before_state=action.before_state,
        affected_type=action.affected_type,
        affected_id=action.affected_id,
        rejection_reason=action.rejection_reason,
        error=action.error,
        expires_at=action.expires_at,
        executed_at=action.executed_at,
        undone_at=action.undone_at,
        created_at=action.created_at,
    )


def _to_audit(entry: AiAuditLog) -> AuditEntryResponse:
    return AuditEntryResponse(
        id=entry.id,
        action_id=entry.action_id,
        tool_name=entry.tool_name,
        affected_type=entry.affected_type,
        affected_id=entry.affected_id,
        before_state=entry.before_state,
        after_state=entry.after_state,
        model=entry.model,
        thread_id=entry.thread_id,
        user_id=entry.user_id,
        created_at=entry.created_at,
    )


async def _load(service: AiActionService, action_id: uuid.UUID, user: User) -> AiAction:
    action = await get_or_404(lambda: service.actions.get_by_id(action_id), _NOT_FOUND)
    if action.user_id != user.id:
        # Regra 3: nem ver a proposta de outro faz sentido — decidir é do dono, e a
        # auditoria do que FOI executado é a rota /ai/audit.
        raise HTTPException(status_code=403, detail=_FORBIDDEN)
    return action


@router.get("/actions")
async def list_actions(
    status: (
        Literal["pending", "approved", "rejected", "executed", "failed", "expired"] | None
    ) = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> ActionListResponse:
    service = AiActionService(session=session, tenant_id=current_user.tenant_id)
    rows = list(
        await service.actions.list_for_user(user_id=current_user.id, status=status, limit=limit)
    )
    return ActionListResponse(items=[_to_action(row) for row in rows], total=len(rows))


@router.get("/actions/{action_id}")
async def get_action(
    action_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> ActionResponse:
    service = AiActionService(session=session, tenant_id=current_user.tenant_id)
    return _to_action(await _load(service, action_id, current_user))


@router.post("/actions/{action_id}/approve")
async def approve_action(
    action_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> ActionResponse:
    """O único caminho pelo qual uma escrita proposta pela IA acontece."""
    service = AiActionService(session=session, tenant_id=current_user.tenant_id)
    action = await _load(service, action_id, current_user)
    config = AiConfigService(session=session, tenant_id=current_user.tenant_id)
    feature = await config.resolve("copilot")
    try:
        await service.approve(action, user=current_user, model=feature.model)
    except ActionForbiddenError as exc:
        raise HTTPException(status_code=403, detail=_FORBIDDEN) from exc
    except ActionNotPendingError as exc:
        raise HTTPException(
            status_code=409, detail="Esta ação já foi decidida ou expirou."
        ) from exc
    return _to_action(action)


@router.post("/actions/{action_id}/reject")
async def reject_action(
    action_id: uuid.UUID,
    payload: RejectRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> ActionResponse:
    service = AiActionService(session=session, tenant_id=current_user.tenant_id)
    action = await _load(service, action_id, current_user)
    try:
        await service.reject(action, user=current_user, reason=payload.reason)
    except ActionForbiddenError as exc:
        raise HTTPException(status_code=403, detail=_FORBIDDEN) from exc
    except ActionNotPendingError as exc:
        raise HTTPException(
            status_code=409, detail="Esta ação já foi decidida ou expirou."
        ) from exc
    return _to_action(action)


@router.post("/actions/{action_id}/undo")
async def undo_action(
    action_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> ActionResponse:
    """Regra 10: janela de 5 minutos, e só se ninguém mexeu no registro depois."""
    service = AiActionService(session=session, tenant_id=current_user.tenant_id)
    action = await _load(service, action_id, current_user)
    try:
        await service.undo(action, user=current_user)
    except ActionForbiddenError as exc:
        raise HTTPException(status_code=403, detail=_FORBIDDEN) from exc
    except UndoNotAllowedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _to_action(action)


@router.get("/audit")
async def list_audit(
    affected_type: str | None = Query(default=None),
    affected_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    _current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> AuditListResponse:
    """O histórico do que a IA gravou num registro (regra 9 na UI: é o que o badge
    abre). Visível a todo o escritório de propósito — é auditoria, não conversa."""
    service = AiActionService(session=session, tenant_id=_current_user.tenant_id)
    rows = list(
        await service.audit.list_for_record(
            affected_type=affected_type, affected_id=affected_id, limit=limit
        )
    )
    return AuditListResponse(items=[_to_audit(row) for row in rows], total=len(rows))
