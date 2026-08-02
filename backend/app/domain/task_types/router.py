import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidTransferError
from app.core.http import get_or_404, parse_active_status
from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.task_types.exceptions import (
    StepNotFoundError,
    SystemTaskTypeError,
    TaskTypeInUseError,
    TaskTypeNameAlreadyExistsError,
)
from app.domain.task_types.models import TaskType
from app.domain.task_types.schemas import (
    SuggestRewardRequest,
    SuggestRewardResponse,
    TaskTypeCreateRequest,
    TaskTypeListResponse,
    TaskTypeResponse,
    TaskTypeTransferRequest,
    TaskTypeUpdateRequest,
)
from app.domain.task_types.score import suggest_reward
from app.domain.task_types.service import TaskTypeService
from app.domain.users.models import User

router = APIRouter(prefix="/task-types", tags=["task-types"])

_NOT_FOUND_DETAIL = "Tipo de tarefa não encontrado."


def _to_response(task_type: TaskType, step_name: str | None) -> TaskTypeResponse:
    return TaskTypeResponse(
        id=task_type.id,
        name=task_type.name,
        step_id=task_type.step_id,
        step_name=step_name,
        complexity=task_type.complexity,
        duration=task_type.duration,
        reward=task_type.reward,
        show_in_schedule=task_type.show_in_schedule,
        is_system=task_type.is_system,
        is_active=task_type.is_active,
        # Regra 9: derivada — tarefas só existem na spec 032, até lá sempre None.
        last_assigned_at=None,
        created_at=task_type.created_at,
    )


@router.get("")
async def list_task_types(
    step_id: int | None = Query(default=None),
    status_: Literal["active", "inactive"] | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> TaskTypeListResponse:
    service = TaskTypeService(session=session, tenant_id=current_user.tenant_id)
    items = await service.list_types(
        step_id=step_id, is_active=parse_active_status(status_), query=q
    )
    # As 9 fases são catálogo global — um dict em memória evita N+1 no step_name.
    step_names = {step.id: step.name for step in await service.steps.list_all()}
    return TaskTypeListResponse(
        items=[
            _to_response(item, step_names.get(item.step_id) if item.step_id is not None else None)
            for item in items
        ],
        total=len(items),
    )


@router.post("", status_code=201)
async def create_task_type(
    payload: TaskTypeCreateRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> TaskTypeResponse:
    # Regra 1: só GESTOR escreve no catálogo — Administrador e Colaborador só leem.
    service = TaskTypeService(session=session, tenant_id=current_user.tenant_id)
    try:
        task_type = await service.create(payload)
    except TaskTypeNameAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail="Já existe um tipo com esse nome.") from exc
    except StepNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Fase não encontrada.") from exc
    step = (
        await service.steps.get_by_step_id(task_type.step_id)
        if task_type.step_id is not None
        else None
    )
    return _to_response(task_type, step.name if step else None)


@router.post("/suggest-reward")
async def suggest_task_reward(
    payload: SuggestRewardRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> SuggestRewardResponse:
    # Regra 2: sugestão determinística da matriz — o campo continua editável.
    return SuggestRewardResponse(reward=suggest_reward(payload.complexity, payload.duration))


@router.post("/transfer")
async def transfer_task_types(
    payload: TaskTypeTransferRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> dict[str, int]:
    service = TaskTypeService(session=session, tenant_id=current_user.tenant_id)
    try:
        transferred = await service.transfer(from_id=payload.from_id, to_id=payload.to_id)
    except InvalidTransferError as exc:
        raise HTTPException(
            status_code=422, detail="from_id/to_id inválidos — precisam ser tipos distintos."
        ) from exc
    return {"transferred_count": transferred}


@router.put("/{task_type_id}")
async def update_task_type(
    task_type_id: uuid.UUID,
    payload: TaskTypeUpdateRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> TaskTypeResponse:
    service = TaskTypeService(session=session, tenant_id=current_user.tenant_id)
    task_type = await get_or_404(lambda: service.get(task_type_id), _NOT_FOUND_DETAIL)
    try:
        updated = await service.update(task_type, payload)
    except SystemTaskTypeError as exc:
        raise HTTPException(
            status_code=403, detail="Tarefa sistêmica não pode ser renomeada."
        ) from exc
    except TaskTypeNameAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail="Já existe um tipo com esse nome.") from exc
    except StepNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Fase não encontrada.") from exc
    step = (
        await service.steps.get_by_step_id(updated.step_id) if updated.step_id is not None else None
    )
    return _to_response(updated, step.name if step else None)


@router.delete("/{task_type_id}", status_code=204)
async def delete_task_type(
    task_type_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    service = TaskTypeService(session=session, tenant_id=current_user.tenant_id)
    task_type = await get_or_404(lambda: service.get(task_type_id), _NOT_FOUND_DETAIL)
    try:
        await service.delete(task_type)
    except SystemTaskTypeError as exc:
        raise HTTPException(
            status_code=403, detail="Tarefa sistêmica não pode ser excluída."
        ) from exc
    except TaskTypeInUseError as exc:
        raise HTTPException(
            status_code=409,
            detail="Tipo de tarefa em uso — transfira as tarefas antes de excluir.",
        ) from exc
