import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http import get_or_404
from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.users.models import User
from app.domain.workflows.service import (
    AlreadyAppliedError,
    InactiveAssigneeError,
    LawsuitNotFoundError,
    WorkflowNameConflictError,
    WorkflowService,
    WorkflowStepReferenceError,
)

router = APIRouter(tags=["workflows"])

_NOT_FOUND_DETAIL = "Workflow não encontrado."
_LAWSUIT_NOT_FOUND_DETAIL = "Processo não encontrado."


class WorkflowStepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type_id: uuid.UUID
    user_id: uuid.UUID | None = None
    days_offset: int | None = Field(default=None, ge=0, le=365)


class WorkflowUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    is_active: bool = True
    # Regra 1: toda etapa tem tipo; responsável e prazo são opcionais. A posição é a
    # ordem do array (regra 11).
    steps: list[WorkflowStepRequest] = []


class WorkflowStepResponse(BaseModel):
    task_type_id: uuid.UUID
    task_type_name: str
    user_id: uuid.UUID | None
    user_name: str | None
    days_offset: int | None


class WorkflowListItemResponse(BaseModel):
    id: uuid.UUID
    name: str
    is_active: bool
    step_count: int


class WorkflowListResponse(BaseModel):
    items: list[WorkflowListItemResponse]


class WorkflowDetailResponse(BaseModel):
    id: uuid.UUID
    name: str
    is_active: bool
    steps: list[WorkflowStepResponse]


class WorkflowApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lawsuit_id: uuid.UUID
    confirm_duplicate: bool = False


class PreviewTaskResponse(BaseModel):
    task_type_name: str
    user_id: uuid.UUID
    user_name: str
    date: date | None


class SkippedStepResponse(BaseModel):
    task_type_name: str
    reason: str


class WorkflowPreviewResponse(BaseModel):
    tasks: list[PreviewTaskResponse]
    skipped: list[SkippedStepResponse]
    already_applied: bool


class WorkflowApplyResponse(BaseModel):
    created: int
    post_ids: list[uuid.UUID]
    skipped: list[SkippedStepResponse]


class HolidayResponse(BaseModel):
    date: date
    name: str


class HolidayListResponse(BaseModel):
    items: list[HolidayResponse]


def _step_tuples(
    payload: WorkflowUpsertRequest,
) -> list[tuple[uuid.UUID, uuid.UUID | None, int | None]]:
    return [(step.task_type_id, step.user_id, step.days_offset) for step in payload.steps]


def _handle_write_errors(exc: Exception) -> HTTPException:
    if isinstance(exc, WorkflowNameConflictError):
        return HTTPException(status_code=409, detail="Já existe um workflow com esse nome.")
    return HTTPException(status_code=422, detail=str(exc))


@router.get("/workflows", response_model=WorkflowListResponse)
async def list_workflows(
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    _current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> WorkflowListResponse:
    service = WorkflowService(session=session, tenant_id=_current_user.tenant_id)
    rows = await service.workflows.list_filtered(status=status, q=q)
    return WorkflowListResponse(
        items=[
            WorkflowListItemResponse(
                id=workflow.id, name=workflow.name, is_active=workflow.is_active, step_count=count
            )
            for workflow, count in rows
        ]
    )


@router.post("/workflows", response_model=WorkflowDetailResponse, status_code=201)
async def create_workflow(
    payload: WorkflowUpsertRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> WorkflowDetailResponse:
    service = WorkflowService(session=session, tenant_id=current_user.tenant_id)
    try:
        workflow = await service.create(payload.name, _step_tuples(payload))
    except (WorkflowNameConflictError, WorkflowStepReferenceError) as exc:
        raise _handle_write_errors(exc) from exc
    return await get_workflow(workflow.id, current_user, session)


@router.get("/workflows/{workflow_id}", response_model=WorkflowDetailResponse)
async def get_workflow(
    workflow_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> WorkflowDetailResponse:
    service = WorkflowService(session=session, tenant_id=current_user.tenant_id)
    workflow = await get_or_404(lambda: service.workflows.get_by_id(workflow_id), _NOT_FOUND_DETAIL)
    steps = (await service.workflows.steps_for([workflow.id])).get(workflow.id, [])
    type_names = await service.task_types.names_for({step.task_type_id for step in steps})
    user_names = await service.users.names_for(
        {step.user_id for step in steps if step.user_id is not None}
    )
    return WorkflowDetailResponse(
        id=workflow.id,
        name=workflow.name,
        is_active=workflow.is_active,
        steps=[
            WorkflowStepResponse(
                task_type_id=step.task_type_id,
                task_type_name=type_names.get(step.task_type_id, ""),
                user_id=step.user_id,
                user_name=user_names.get(step.user_id) if step.user_id else None,
                days_offset=step.days_offset,
            )
            for step in steps
        ],
    )


@router.put("/workflows/{workflow_id}", response_model=WorkflowDetailResponse)
async def update_workflow(
    workflow_id: uuid.UUID,
    payload: WorkflowUpsertRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> WorkflowDetailResponse:
    service = WorkflowService(session=session, tenant_id=current_user.tenant_id)
    workflow = await get_or_404(lambda: service.workflows.get_by_id(workflow_id), _NOT_FOUND_DETAIL)
    try:
        await service.update(
            workflow,
            name=payload.name,
            is_active=payload.is_active,
            steps=_step_tuples(payload),
        )
    except (WorkflowNameConflictError, WorkflowStepReferenceError) as exc:
        raise _handle_write_errors(exc) from exc
    return await get_workflow(workflow.id, current_user, session)


@router.delete("/workflows/{workflow_id}", status_code=204)
async def delete_workflow(
    workflow_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    """Regra 9: excluir não afeta tarefas já criadas — posts nunca referenciam o
    workflow, e etapas de processo (stages) ficam NULL via ON DELETE SET NULL."""
    service = WorkflowService(session=session, tenant_id=current_user.tenant_id)
    workflow = await get_or_404(lambda: service.workflows.get_by_id(workflow_id), _NOT_FOUND_DETAIL)
    await service.workflows.delete(workflow)


@router.post("/workflows/{workflow_id}/preview", response_model=WorkflowPreviewResponse)
async def preview_workflow(
    workflow_id: uuid.UUID,
    payload: WorkflowApplyRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> WorkflowPreviewResponse:
    """Regra 6: preview não persiste NADA — mesma resolução do apply, mesmo dia base."""
    service = WorkflowService(session=session, tenant_id=current_user.tenant_id)
    workflow = await get_or_404(lambda: service.workflows.get_by_id(workflow_id), _NOT_FOUND_DETAIL)
    try:
        preview = await service.preview(workflow, payload.lawsuit_id, date.today())
    except LawsuitNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_LAWSUIT_NOT_FOUND_DETAIL) from exc
    return WorkflowPreviewResponse(
        tasks=[
            PreviewTaskResponse(
                task_type_name=task.task_type_name,
                user_id=task.user_id,
                user_name=task.user_name,
                date=task.date,
            )
            for task in preview.tasks
        ],
        skipped=[
            SkippedStepResponse(task_type_name=item.task_type_name, reason=item.reason)
            for item in preview.skipped
        ],
        already_applied=preview.already_applied,
    )


@router.post("/workflows/{workflow_id}/apply", response_model=WorkflowApplyResponse)
async def apply_workflow(
    workflow_id: uuid.UUID,
    payload: WorkflowApplyRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> WorkflowApplyResponse:
    service = WorkflowService(session=session, tenant_id=current_user.tenant_id)
    workflow = await get_or_404(lambda: service.workflows.get_by_id(workflow_id), _NOT_FOUND_DETAIL)
    try:
        result = await service.apply(
            workflow,
            payload.lawsuit_id,
            current_user,
            date.today(),
            confirm_duplicate=payload.confirm_duplicate,
        )
    except LawsuitNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_LAWSUIT_NOT_FOUND_DETAIL) from exc
    except AlreadyAppliedError as exc:
        raise HTTPException(
            status_code=409,
            detail="Este workflow já gerou tarefas neste processo. Confirme para aplicar de novo.",
        ) from exc
    except InactiveAssigneeError as exc:
        raise HTTPException(
            status_code=422, detail="Um responsável configurado está inativo — nada foi criado."
        ) from exc
    return WorkflowApplyResponse(
        created=len(result.created_ids),
        post_ids=result.created_ids,
        skipped=[
            SkippedStepResponse(task_type_name=item.task_type_name, reason=item.reason)
            for item in result.skipped
        ],
    )


@router.get("/holidays", response_model=HolidayListResponse)
async def list_holidays(
    year: int | None = Query(default=None, ge=2020, le=2100),
    _current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> HolidayListResponse:
    service = WorkflowService(session=session, tenant_id=_current_user.tenant_id)
    holidays = await service.holidays.list_dates(year=year)
    return HolidayListResponse(
        items=[HolidayResponse(date=holiday.date, name=holiday.name) for holiday in holidays]
    )
