"""Rotas de automação (spec 092 §5)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.automations.conditions import InvalidConditionError
from app.domain.automations.engine import AutomationEngine, AutomationLimitError
from app.domain.automations.models import Automation
from app.domain.automations.schemas import (
    ActionResponse,
    AutomationListResponse,
    AutomationRequest,
    AutomationResponse,
    RunListResponse,
    RunResponse,
    RunStepResponse,
    SimulatedStepResponse,
    TestRequest,
    TestResponse,
    ToggleRequest,
)
from app.domain.automations.service import (
    ActionInput,
    AutomationNameConflictError,
    AutomationService,
    UnknownActionKindError,
    UnknownTriggerError,
)
from app.domain.users.models import User

router = APIRouter(prefix="/automations", tags=["automations"])

_NOT_FOUND = "Automação não encontrada."


def _to_inputs(payload: AutomationRequest) -> list[ActionInput]:
    return [
        ActionInput(
            action_kind=item.action_kind,
            action_config=item.action_config,
            delay_kind=item.delay_kind,
            delay_value=item.delay_value,
            condition=item.condition,
        )
        for item in payload.actions
    ]


async def _to_response(service: AutomationService, automation: Automation) -> AutomationResponse:
    acoes = await service.actions_of(automation)
    return AutomationResponse(
        id=automation.id,
        name=automation.name,
        description=automation.description,
        trigger_kind=automation.trigger_kind,
        trigger_config=automation.trigger_config,
        is_active=automation.is_active,
        created_by=automation.created_by,
        created_at=automation.created_at,
        actions=[
            ActionResponse(
                id=acao.id,
                position=acao.position,
                action_kind=acao.action_kind,
                action_config=acao.action_config,
                delay_kind=acao.delay_kind,
                delay_value=acao.delay_value,
                condition=acao.condition,
            )
            for acao in acoes
        ],
    )


async def _get(session: AsyncSession, automation_id: uuid.UUID) -> Automation:
    automation = await session.get(Automation, automation_id)
    if automation is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return automation


def _handle(exc: Exception) -> HTTPException:
    if isinstance(exc, AutomationNameConflictError):
        return HTTPException(status_code=409, detail="Já existe uma automação com este nome.")
    if isinstance(exc, UnknownTriggerError):
        return HTTPException(status_code=422, detail=f"Gatilho desconhecido: {exc}.")
    if isinstance(exc, UnknownActionKindError):
        return HTTPException(status_code=422, detail=f"Ação desconhecida: {exc}.")
    if isinstance(exc, AutomationLimitError | InvalidConditionError):
        return HTTPException(status_code=422, detail=str(exc))
    raise exc


@router.get("")
async def list_automations(
    status: str | None = Query(default=None, pattern="^(active|inactive)$"),
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> AutomationListResponse:
    service = AutomationService(session, current_user.tenant_id)
    only_active = None if status is None else status == "active"
    automations = await service.automations.list_all(only_active=only_active)
    items = [await _to_response(service, automation) for automation in automations]
    return AutomationListResponse(items=items, total=len(items))


@router.post("", status_code=201)
async def create_automation(
    payload: AutomationRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> AutomationResponse:
    service = AutomationService(session, current_user.tenant_id)
    try:
        automation = await service.create(
            name=payload.name,
            description=payload.description,
            trigger_kind=payload.trigger_kind,
            trigger_config=payload.trigger_config,
            actions=_to_inputs(payload),
            created_by=current_user.id,
        )
    except Exception as exc:  # noqa: BLE001 - traduzido em _handle
        raise _handle(exc) from exc
    return await _to_response(service, automation)


@router.put("/{automation_id}")
async def update_automation(
    automation_id: uuid.UUID,
    payload: AutomationRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> AutomationResponse:
    service = AutomationService(session, current_user.tenant_id)
    automation = await _get(session, automation_id)
    try:
        await service.update(
            automation,
            name=payload.name,
            description=payload.description,
            trigger_kind=payload.trigger_kind,
            trigger_config=payload.trigger_config,
            actions=_to_inputs(payload),
        )
    except Exception as exc:  # noqa: BLE001 - traduzido em _handle
        raise _handle(exc) from exc
    return await _to_response(service, automation)


@router.delete("/{automation_id}", status_code=204)
async def delete_automation(
    automation_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    automation = await _get(session, automation_id)
    await session.delete(automation)


@router.post("/{automation_id}/toggle")
async def toggle_automation(
    automation_id: uuid.UUID,
    payload: ToggleRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> AutomationResponse:
    service = AutomationService(session, current_user.tenant_id)
    automation = await _get(session, automation_id)
    await service.toggle(automation, is_active=payload.is_active)
    return await _to_response(service, automation)


@router.post("/{automation_id}/test")
async def test_automation(
    automation_id: uuid.UUID,
    payload: TestRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> TestResponse:
    """Regra 10: simula tudo e não persiste nada."""
    automation = await _get(session, automation_id)
    engine = AutomationEngine(session, current_user.tenant_id)
    passos = await engine.simulate(automation, payload.payload)
    return TestResponse(
        steps=[
            SimulatedStepResponse(
                position=passo.position,
                action_kind=passo.action_kind,
                status=passo.status,
                detail=passo.detail,
                scheduled_for=passo.scheduled_for.isoformat() if passo.scheduled_for else None,
            )
            for passo in passos
        ]
    )


@router.get("/{automation_id}/runs")
async def list_runs(
    automation_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> RunListResponse:
    service = AutomationService(session, current_user.tenant_id)
    automation = await _get(session, automation_id)
    execucoes = await service.runs_of(automation, limit=limit)
    items = []
    for run in execucoes:
        passos = await service.steps_of(run)
        items.append(
            RunResponse(
                id=run.id,
                automation_id=run.automation_id,
                subject_type=run.subject_type,
                subject_id=run.subject_id,
                status=run.status,
                actions_completed=run.actions_completed,
                chain_depth=run.chain_depth,
                next_position=run.next_position,
                next_action_at=run.next_action_at,
                error=run.error,
                started_at=run.started_at,
                finished_at=run.finished_at,
                steps=[
                    RunStepResponse(
                        position=passo.position,
                        action_kind=passo.action_kind,
                        status=passo.status,
                        detail=passo.detail,
                        error=passo.error,
                        created_at=passo.created_at,
                    )
                    for passo in passos
                ],
            )
        )
    return RunListResponse(items=items, total=len(items))
