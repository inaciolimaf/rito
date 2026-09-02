"""Rotas de automação (spec 092 §5)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import UserRole, require_role
from app.domain.ai.router import get_llm_provider
from app.domain.ai.service import AiRunner
from app.domain.auth.deps import get_session_for_current_user
from app.domain.automations.conditions import InvalidConditionError
from app.domain.automations.decision import DecisionRunner
from app.domain.automations.engine import AutomationEngine, AutomationLimitError
from app.domain.automations.models import (
    ActionKind,
    Automation,
    AutomationRun,
)
from app.domain.automations.schemas import (
    ActionResponse,
    AiBudgetRequest,
    AutomationListResponse,
    AutomationRequest,
    AutomationResponse,
    DecisionListResponse,
    DecisionResponse,
    RunListResponse,
    RunResponse,
    RunStepResponse,
    SimulateDecisionRequest,
    SimulateDecisionResponse,
    SimulatedStepResponse,
    TestRequest,
    TestResponse,
    ToggleRequest,
)
from app.domain.automations.service import (
    ActionInput,
    AutomationNameConflictError,
    AutomationService,
    DecisionConfigError,
    UnknownActionKindError,
    UnknownTriggerError,
)
from app.domain.users.models import User
from app.integrations.openrouter.types import LLMProvider

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
            branches=item.branches,
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
        monthly_ai_budget_usd=(
            float(automation.monthly_ai_budget_usd)
            if automation.monthly_ai_budget_usd is not None
            else None
        ),
        current_month_spend_usd=float(automation.current_month_spend_usd or 0),
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
                branches=acao.branches,
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
    if isinstance(exc, AutomationLimitError | InvalidConditionError | DecisionConfigError):
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
    except Exception as exc:
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
    except Exception as exc:
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


@router.put("/{automation_id}/ai-budget")
async def set_ai_budget(
    automation_id: uuid.UUID,
    payload: AiBudgetRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> AutomationResponse:
    """Regra 6: teto de IA por automação — o que protege de UMA regra mal escrita."""
    service = AutomationService(session, current_user.tenant_id)
    automation = await _get(session, automation_id)
    automation.monthly_ai_budget_usd = payload.monthly_ai_budget_usd
    await session.flush()
    return await _to_response(service, automation)


@router.get("/{automation_id}/decisions")
async def list_decisions(
    automation_id: uuid.UUID,
    run_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> DecisionListResponse:
    """O raciocínio de cada decisão (regra 4) — é o que torna a automação auditável."""
    await _get(session, automation_id)
    service = AutomationService(session, current_user.tenant_id)
    decisoes = await service.list_decisions(automation_id=automation_id, run_id=run_id, limit=limit)
    return DecisionListResponse(
        items=[
            DecisionResponse(
                id=item.id,
                run_id=item.run_id,
                action_id=item.action_id,
                question=item.question,
                context_summary=item.context_summary,
                chosen_branch=item.chosen_branch,
                confidence=float(item.confidence) if item.confidence is not None else None,
                reasoning=item.reasoning,
                model=item.model,
                tokens_used=item.tokens_used,
                cost_usd=float(item.cost_usd) if item.cost_usd is not None else None,
                fell_back=item.fell_back,
                fallback_reason=item.fallback_reason,
                created_at=item.created_at,
            )
            for item in decisoes
        ],
        total=len(decisoes),
    )


@router.post("/{automation_id}/decisions/simulate")
async def simulate_decision(
    automation_id: uuid.UUID,
    payload: SimulateDecisionRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> SimulateDecisionResponse:
    """Regra 10: roda a decisão de verdade e NÃO executa as ações do ramo.

    A decisão acontece mesmo — é o ponto: quem está escrevendo a automação precisa ver
    o modelo escolher com o contexto real antes de deixar a regra no ar.
    """
    service = AutomationService(session, current_user.tenant_id)
    automation = await _get(session, automation_id)
    acoes = await service.actions_of(automation)
    decisoes = [item for item in acoes if item.action_kind == ActionKind.LLM_DECISION.value]
    if payload.position is not None:
        decisoes = [item for item in decisoes if item.position == payload.position]
    if not decisoes:
        raise HTTPException(
            status_code=422, detail="Esta automação não tem um nó de decisão por IA."
        )
    action = decisoes[0]

    engine = AutomationEngine(
        session,
        current_user.tenant_id,
        ai_runner=AiRunner(session, current_user.tenant_id, provider),
    )
    run = AutomationRun(
        tenant_id=current_user.tenant_id,
        automation_id=automation.id,
        trigger_payload=payload.payload,
        status="done",
    )
    session.add(run)
    await session.flush()
    outcome = await DecisionRunner(engine).decide(
        run=run, action=action, automation=automation, actor=current_user, persist=False
    )
    # A execução de simulação não vira histórico: ela existiu só para carregar o payload.
    await session.delete(run)
    await session.flush()
    return SimulateDecisionResponse(
        position=action.position,
        question=str((action.action_config or {}).get("question", "")),
        chosen_branch=outcome.branch,
        confidence=outcome.confidence,
        reasoning=outcome.reasoning,
        fell_back=outcome.fell_back,
        fallback_reason=outcome.fallback_reason,
    )
