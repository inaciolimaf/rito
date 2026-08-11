import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidTransferError
from app.core.http import get_or_404, parse_active_status
from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.stages.exceptions import (
    InvalidReorderError,
    StageNameAlreadyExistsError,
    StepNotFoundError,
)
from app.domain.stages.models import Stage
from app.domain.stages.schemas import (
    ReorderStagesRequest,
    StageCreateRequest,
    StageListResponse,
    StageResponse,
    StageUpdateRequest,
    StepResponse,
    TransferStagesRequest,
)
from app.domain.stages.service import StageService, StepService
from app.domain.users.models import User
from app.workers.stagnation import schedule_stage_recalculation

steps_router = APIRouter(prefix="/steps", tags=["steps"])
stages_router = APIRouter(prefix="/stages", tags=["stages"])


def _stage_to_response(stage: Stage, step_name: str) -> StageResponse:
    return StageResponse(
        id=stage.id,
        name=stage.name,
        step_id=stage.step_id,
        step_name=step_name,
        position=stage.position,
        enable_stagnant_days=stage.enable_stagnant_days,
        stagnant_days=stage.stagnant_days,
        suggested_workflow_id=stage.suggested_workflow_id,
        is_active=stage.is_active,
        created_at=stage.created_at,
    )


@steps_router.get("")
async def list_steps(
    _current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> list[StepResponse]:
    """Regra 1: as 9 fases são imutáveis — só leitura, sem POST/PUT/DELETE nesta rota."""
    steps = await StepService(session).list_steps()
    return [StepResponse(id=step.id, name=step.name, position=step.position) for step in steps]


@stages_router.get("")
async def list_stages(
    step_id: int | None = Query(default=None),
    status_: Literal["active", "inactive"] | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> StageListResponse:
    service = StageService(session=session, tenant_id=current_user.tenant_id)
    items = await service.list_stages(
        step_id=step_id, is_active=parse_active_status(status_), query=q
    )
    return StageListResponse(
        items=[_stage_to_response(stage, step_name) for stage, step_name in items],
        total=len(items),
    )


@stages_router.post("", status_code=201)
async def create_stage(
    payload: StageCreateRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> StageResponse:
    service = StageService(session=session, tenant_id=current_user.tenant_id)
    try:
        stage, step_name = await service.create(payload)
    except StageNameAlreadyExistsError as exc:
        raise HTTPException(
            status_code=409, detail="Já existe uma etapa com esse nome nesta fase."
        ) from exc
    except StepNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Fase não encontrada.") from exc
    return _stage_to_response(stage, step_name)


@stages_router.put("/{stage_id}")
async def update_stage(
    stage_id: uuid.UUID,
    payload: StageUpdateRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> StageResponse:
    service = StageService(session=session, tenant_id=current_user.tenant_id)
    stage, _ = await get_or_404(lambda: service.get(stage_id), "Etapa não encontrada.")
    previous_rule = (stage.enable_stagnant_days, stage.stagnant_days)

    try:
        updated, step_name = await service.update(stage, payload)
    except StageNameAlreadyExistsError as exc:
        raise HTTPException(
            status_code=409, detail="Já existe uma etapa com esse nome nesta fase."
        ) from exc
    except StepNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Fase não encontrada.") from exc
    # Spec 052, regra 10: só recalcula quando a regra de estagnação de fato mudou.
    if (updated.enable_stagnant_days, updated.stagnant_days) != previous_rule:
        schedule_stage_recalculation(updated.id, current_user.tenant_id)
    return _stage_to_response(updated, step_name)


@stages_router.delete("/{stage_id}", status_code=204)
async def delete_stage(
    stage_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    service = StageService(session=session, tenant_id=current_user.tenant_id)
    stage, _ = await get_or_404(lambda: service.get(stage_id), "Etapa não encontrada.")
    await service.delete(stage)


@stages_router.post("/reorder")
async def reorder_stages(
    payload: ReorderStagesRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> dict[str, int]:
    service = StageService(session=session, tenant_id=current_user.tenant_id)
    try:
        await service.reorder(payload.stage_ids)
    except InvalidReorderError as exc:
        raise HTTPException(
            status_code=422,
            detail="Os ids precisam existir e pertencer todos à mesma fase.",
        ) from exc
    return {"reordered_count": len(payload.stage_ids)}


@stages_router.post("/transfer")
async def transfer_stages(
    payload: TransferStagesRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> dict[str, int]:
    service = StageService(session=session, tenant_id=current_user.tenant_id)
    try:
        transferred = await service.transfer(from_id=payload.from_id, to_id=payload.to_id)
    except InvalidTransferError as exc:
        raise HTTPException(
            status_code=422, detail="from_id/to_id inválidos — precisam ser etapas distintas."
        ) from exc
    return {"transferred_count": transferred}
