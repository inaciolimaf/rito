import uuid
from collections.abc import Mapping
from typing import Literal, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock
from app.core.config import get_settings
from app.core.deps import get_messaging_channels, get_redis
from app.core.http import get_or_404, parse_month_query
from app.core.locks import RedisSyncLock
from app.core.permissions import FinancialAccess, UserRole, require_financial, require_role
from app.domain.auth.deps import get_clock, get_session_for_current_user
from app.domain.datajud.exceptions import LawsuitSyncInProgressError
from app.domain.datajud.movement_sync_service import MovementSyncService, sync_lock_key
from app.domain.datajud.service import DatajudService, LawsuitSyncRunService
from app.domain.lawsuits.board_service import BoardService
from app.domain.lawsuits.cnj import SEGMENT_NAMES, CNJValidationError
from app.domain.lawsuits.exceptions import (
    CourtSystemIncompatibleError,
    DuplicatePartyError,
    FolderMergeNotConfirmedError,
    FolderNotFoundError,
    LastPartyError,
    LawsuitNotFoundError,
    LawsuitTypeNotFoundError,
    MovementNotAuthorError,
    NotResponsibleForLawsuitError,
    PartyCustomerNotFoundError,
    ResponsibleNotActiveError,
    StageNotFoundError,
    TribunalMovementImmutableError,
    WorkflowAlreadyAppliedError,
    WorkflowApplicationNotFoundError,
    WorkflowUndoHasCompletedTaskError,
    WorkflowUndoWindowExpiredError,
)
from app.domain.lawsuits.export import build_pdf, build_xlsx
from app.domain.lawsuits.folders import FolderService
from app.domain.lawsuits.listing import LawsuitListRow
from app.domain.lawsuits.models import Lawsuit, LawsuitMovement
from app.domain.lawsuits.movements_service import MovementsService
from app.domain.lawsuits.parties_service import PartiesService, PartyDetail
from app.domain.lawsuits.schemas import (
    TIMELINE_KINDS,
    ApplyWorkflowRequest,
    ApplyWorkflowResponse,
    BulkMoveStageRequest,
    BulkMoveStageResponse,
    ClosureGoalResponse,
    FinancialSummaryResponse,
    FolderGroupItemResponse,
    FolderGroupResponse,
    FolderRenameRequest,
    FolderRenameResponse,
    FolderSuggestionResponse,
    InferredCourtResponse,
    LawsuitCreateRequest,
    LawsuitExportRequest,
    LawsuitFiltersQuery,
    LawsuitGroupsResponse,
    LawsuitListItemResponse,
    LawsuitListResponse,
    LawsuitResponse,
    LawsuitStatsResponse,
    LawsuitUpdateRequest,
    MovementCreateRequest,
    MovementResponse,
    MovementUpdateRequest,
    MoveStageRequest,
    MoveStageResponse,
    ParsedCNJResponse,
    PartyBriefResponse,
    PartyCreateRequest,
    PartyResponse,
    PartyUpdateRequest,
    SkippedWorkflowStepResponse,
    StatsCardResponse,
    StepVolumeResponse,
    SuggestedWorkflowResponse,
    SuppressWorkflowRequest,
    SyncMovementsResponse,
    SyncRunListResponse,
    SyncRunResponse,
    SyncStatusResponse,
    TimelineItemResponse,
    TimelineResponse,
    ValidateNumberRequest,
    ValidateNumberResponse,
    WorkflowApplicationListResponse,
    WorkflowApplicationResponse,
)
from app.domain.lawsuits.service import LawsuitDetail, LawsuitService
from app.domain.lawsuits.stats import invalidate_stats_cache
from app.domain.lawsuits.workflow_service import LawsuitWorkflowService
from app.domain.notifications.dispatch import NotificationDispatcher
from app.domain.notifications.models import NotificationEvent
from app.domain.users.models import User
from app.domain.workflows.service import InactiveAssigneeError
from app.integrations.datajud.client import (
    DatajudClient,
    DatajudConfigError,
    DatajudUnauthorizedError,
)
from app.integrations.http.client import create_http_client
from app.integrations.http.types import HostPolicy
from app.integrations.messaging.base import MessagingChannel
from app.workers.aggregates import schedule_aggregate_refresh

router = APIRouter(prefix="/lawsuits", tags=["lawsuits"])

_DATAJUD_HOST = "api-publica.datajud.cnj.jus.br"

_NOT_FOUND_DETAIL = "Processo não encontrado."
_PARTY_NOT_FOUND_DETAIL = "Parte não encontrada."
_PARTY_CUSTOMER_DETAIL = "Contato não encontrado."
_DUPLICATE_PARTY_DETAIL = "Esta pessoa já está neste polo do processo."
_LAST_PARTY_DETAIL = "O processo precisa de pelo menos uma parte."


def _schedule_cycle_events(previous: tuple[object, object], current: tuple[object, object]) -> None:
    """Spec 078, regra 5: a TRANSIÇÃO para fechado/arquivado agenda o refresh das
    views de BI em até 1 min, sem bloquear a operação que disparou. Criar processo
    já fechado (importação) conta como transição — `previous` (None, None)."""
    prev_closure, prev_archived = previous
    closure, archived = current
    if closure is not None and prev_closure is None:
        schedule_aggregate_refresh("lawsuit.closed")
    if archived is not None and prev_archived is None:
        schedule_aggregate_refresh("lawsuit.archived")


def _raise_party_errors(exc: Exception) -> NoReturn:
    if isinstance(exc, PartyCustomerNotFoundError):
        raise HTTPException(status_code=422, detail=_PARTY_CUSTOMER_DETAIL) from exc
    if isinstance(exc, DuplicatePartyError):
        raise HTTPException(status_code=409, detail=_DUPLICATE_PARTY_DETAIL) from exc
    raise exc


def _to_party_response(detail: PartyDetail) -> PartyResponse:
    party = detail.party
    return PartyResponse(
        id=party.id,
        lawsuit_id=party.lawsuit_id,
        customer_id=party.customer_id,
        customer_name=detail.customer_name,
        pole=party.pole,
        is_client=party.is_client,
        created_at=party.created_at,
    )


def _to_list_item_response(row: LawsuitListRow) -> LawsuitListItemResponse:
    lawsuit = row.lawsuit
    return LawsuitListItemResponse(
        id=lawsuit.id,
        process_number=lawsuit.process_number,
        folder=lawsuit.folder,
        is_archived=lawsuit.is_archived,
        created_at=lawsuit.created_at,
        last_movement_at=lawsuit.last_movement_at,
        last_movement_title=row.last_movement_title,
        lawsuit_type_name=row.lawsuit_type_name,
        action_group_name=row.action_group_name,
        stage_name=row.stage_name,
        parties=[
            PartyBriefResponse(name=str(party["name"]), pole=party["pole"]) for party in row.parties
        ],
        parties_total=row.parties_total,
    )


def _to_movement_response(movement: LawsuitMovement) -> MovementResponse:
    return MovementResponse(
        id=movement.id,
        lawsuit_id=movement.lawsuit_id,
        origin=movement.origin,
        occurred_at=movement.occurred_at,
        title=movement.title,
        body=movement.body,
        header=movement.header,
        external_code=movement.external_code,
        external_id=movement.external_id,
        created_by=movement.created_by,
        created_at=movement.created_at,
    )


def _to_response(detail: LawsuitDetail) -> LawsuitResponse:
    lawsuit = detail.lawsuit
    return LawsuitResponse(
        id=lawsuit.id,
        user_id=lawsuit.user_id,
        lawsuit_type_id=lawsuit.lawsuit_type_id,
        action_group_id=detail.action_group_id,
        action_group_name=detail.action_group_name,
        stage_id=lawsuit.stage_id,
        step_id=detail.step_id,
        step_name=detail.step_name,
        court_id=lawsuit.court_id,
        court_system_id=lawsuit.court_system_id,
        process_number=lawsuit.process_number,
        protocol_number=lawsuit.protocol_number,
        originating_process=lawsuit.originating_process,
        folder=lawsuit.folder,
        filing_year=lawsuit.filing_year,
        judiciary=lawsuit.judiciary,
        county=lawsuit.county,
        court_division=lawsuit.court_division,
        process_date=lawsuit.process_date,
        notes=lawsuit.notes,
        case_value=lawsuit.case_value,
        fees_value=lawsuit.fees_value,
        fees_percentage=lawsuit.fees_percentage,
        contingency=lawsuit.contingency,
        closure_date=lawsuit.closure_date,
        transit_date=lawsuit.transit_date,
        archived_date=lawsuit.archived_date,
        outcome=lawsuit.outcome,
        is_archived=lawsuit.is_archived,
        created_at=lawsuit.created_at,
        updated_at=lawsuit.updated_at,
    )


@router.get("")
async def list_lawsuits(
    # Depends() (não Query()): nesta versão do FastAPI o modelo Pydantic só é expandido
    # em parâmetros de query individuais como dependência — com Query() o modelo inteiro
    # vira UM parâmetro obrigatório chamado "filters".
    filters: LawsuitFiltersQuery = Depends(),
    order: Literal["asc", "desc"] = Query(default="desc"),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    group_by: Literal["folder"] | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> LawsuitListResponse | LawsuitGroupsResponse:
    if group_by == "folder":
        # Visão agrupada por pasta (spec 029 §5) — grupos por contagem decrescente,
        # com "Sem pasta" para os sem valor (regra 6).
        folder_service = FolderService(session)
        groups = await folder_service.group_by_folder()
        return LawsuitGroupsResponse(
            groups=[
                FolderGroupResponse(
                    name=group.name,
                    count=group.count,
                    items=[
                        FolderGroupItemResponse(
                            id=item.id,
                            process_number=item.process_number,
                            is_archived=item.is_archived,
                            created_at=item.created_at,
                        )
                        for item in group.items
                    ],
                )
                for group in groups
            ]
        )
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    items, next_cursor, total = await service.list_lawsuits(
        payload=filters, order=order, cursor=cursor, limit=limit
    )
    return LawsuitListResponse(
        items=[_to_list_item_response(item) for item in items],
        next_cursor=next_cursor,
        total=total,
    )


@router.get("/folders")
async def list_folders(
    q: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=20),
    _current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> list[FolderSuggestionResponse]:
    # Antes de "/{lawsuit_id}" — senão "folders" casaria como UUID e daria 422 de path.
    service = FolderService(session)
    suggestions = await service.search(query=q, limit=limit)
    return [FolderSuggestionResponse(name=str(item.name), count=item.count) for item in suggestions]


@router.post("/folders/rename")
async def rename_folder(
    payload: FolderRenameRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> FolderRenameResponse:
    service = FolderService(session)
    try:
        result = await service.rename(
            from_name=payload.from_name, to_name=payload.to_name, merge=payload.merge
        )
    except FolderNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Pasta não encontrada.") from exc
    except FolderMergeNotConfirmedError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Já existe a pasta '{exc.target}' — confirme a fusão das duas.",
        ) from exc
    return FolderRenameResponse(folder=result.folder, updated=result.updated, merged=result.merged)


@router.get("/stats")
async def get_lawsuits_stats(
    month: str | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    redis: Redis = Depends(get_redis),
    clock: Clock = Depends(get_clock),
) -> LawsuitStatsResponse:
    # Registrada ANTES de "/{lawsuit_id}" — depois dele, "stats" casaria como UUID e
    # daria 422 de path, nunca 200.
    reference = parse_month_query(month, clock.today())
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    stats = await service.get_stats(month=reference, cache=redis)
    return LawsuitStatsResponse(
        active=StatsCardResponse(**vars(stats.active)),
        closed_this_month=StatsCardResponse(**vars(stats.closed_this_month)),
        archived_this_month=StatsCardResponse(**vars(stats.archived_this_month)),
        volume_by_step=[StepVolumeResponse(**vars(item)) for item in stats.volume_by_step],
        closure_goal=(
            ClosureGoalResponse(**vars(stats.closure_goal)) if stats.closure_goal else None
        ),
    )


@router.post("/export")
async def export_lawsuits(
    payload: LawsuitExportRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> Response:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    rows = await service.export_lawsuits(payload=payload.filters)
    content = build_xlsx(rows) if payload.format == "xlsx" else build_pdf(rows)
    media_type = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if payload.format == "xlsx"
        else "application/pdf"
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="processos.{payload.format}"'},
    )


@router.post("", status_code=201)
async def create_lawsuit(
    payload: LawsuitCreateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    redis: Redis = Depends(get_redis),
    channels: Mapping[str, MessagingChannel] = Depends(get_messaging_channels),
    clock: Clock = Depends(get_clock),
) -> LawsuitResponse:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    try:
        created = await service.create(payload)
    except LawsuitTypeNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Tipo de ação não encontrado.") from exc
    except StageNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Etapa não encontrada.") from exc
    except ResponsibleNotActiveError as exc:
        raise HTTPException(
            status_code=422, detail="Responsável precisa ser um usuário ativo do tenant."
        ) from exc
    except CourtSystemIncompatibleError as exc:
        raise HTTPException(
            status_code=422, detail="Sistema processual não pertence ao tribunal selecionado."
        ) from exc
    except (PartyCustomerNotFoundError, DuplicatePartyError) as exc:
        _raise_party_errors(exc)
    except CNJValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # Regra 7 (spec 028): criar processo invalida o cache do dashboard.
    await invalidate_stats_cache(
        redis,
        current_user.tenant_id,
        created.lawsuit.closure_date,
        created.lawsuit.archived_date,
        today=clock.today(),
    )
    # Spec 078, regra 5: processo criado já fechado/arquivado (importação) invalida
    # as views de BI.
    _schedule_cycle_events(
        (None, None), (created.lawsuit.closure_date, created.lawsuit.archived_date)
    )
    dispatcher = NotificationDispatcher(
        session=session, tenant_id=current_user.tenant_id, channels=channels
    )
    await dispatcher.dispatch(
        NotificationEvent.NOVO_PROCESSO,
        title="Novo processo cadastrado",
        body=created.lawsuit.process_number or "Sem número de processo informado",
        link=f"/lawsuits/{created.lawsuit.id}",
    )
    return _to_response(created)


@router.post("/validate-number")
async def validate_number(
    payload: ValidateNumberRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> ValidateNumberResponse:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    result = await service.validate_number(payload.process_number)
    parsed = result.parsed
    return ValidateNumberResponse(
        valid=result.valid,
        formatted=result.formatted,
        parsed=(
            ParsedCNJResponse(
                sequential=parsed.sequential,
                check_digit=parsed.check_digit,
                year=parsed.year,
                segment=parsed.segment,
                segment_name=SEGMENT_NAMES[parsed.segment],
                court=parsed.court,
                origin=parsed.origin,
            )
            if parsed is not None
            else None
        ),
        inferred_court=(
            InferredCourtResponse(
                id=result.inferred_court.id,
                code=result.inferred_court.code,
                name=result.inferred_court.name,
            )
            if result.inferred_court is not None
            else None
        ),
        error=result.error,
    )


@router.post("/bulk/move-stage")
async def bulk_move_lawsuit_stage(
    payload: BulkMoveStageRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> BulkMoveStageResponse:
    """Spec 051, regra 9: transacional — tudo ou nada. Registrada ANTES de
    `/{lawsuit_id}` (regra de ordenação do CLAUDE.md §6 — "bulk" bateria no path
    param dinâmico se viesse depois, como o /counts e /export da 048)."""
    board = BoardService(session=session, tenant_id=current_user.tenant_id)
    try:
        moved = await board.bulk_move_stage(
            payload.lawsuit_ids, stage_id=payload.stage_id, actor=current_user
        )
    except LawsuitNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL) from exc
    except NotResponsibleForLawsuitError as exc:
        raise HTTPException(
            status_code=403, detail="Só o responsável pelo processo pode mover a etapa."
        ) from exc
    except StageNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Etapa não encontrada.") from exc
    return BulkMoveStageResponse(moved=moved)


@router.get("/{lawsuit_id}")
async def get_lawsuit(
    lawsuit_id: uuid.UUID,
    _current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> LawsuitResponse:
    service = LawsuitService(session=session, tenant_id=_current_user.tenant_id)
    detail = await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)
    return _to_response(detail)


@router.put("/{lawsuit_id}")
async def update_lawsuit(
    lawsuit_id: uuid.UUID,
    payload: LawsuitUpdateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    redis: Redis = Depends(get_redis),
    clock: Clock = Depends(get_clock),
) -> LawsuitResponse:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)
    # Datas de ciclo ANTES da mutação — se o fechamento migrou de mês, o cache do mês
    # antigo também precisa cair (regra 7, spec 028).
    previous_cycle_dates = (detail.lawsuit.closure_date, detail.lawsuit.archived_date)
    try:
        updated = await service.update(detail.lawsuit, payload, changed_by=current_user.id)
    except LawsuitTypeNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Tipo de ação não encontrado.") from exc
    except StageNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Etapa não encontrada.") from exc
    except ResponsibleNotActiveError as exc:
        raise HTTPException(
            status_code=422, detail="Responsável precisa ser um usuário ativo do tenant."
        ) from exc
    except CourtSystemIncompatibleError as exc:
        raise HTTPException(
            status_code=422, detail="Sistema processual não pertence ao tribunal selecionado."
        ) from exc
    except CNJValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await invalidate_stats_cache(
        redis,
        current_user.tenant_id,
        *previous_cycle_dates,
        updated.lawsuit.closure_date,
        updated.lawsuit.archived_date,
        today=clock.today(),
    )
    # Spec 078, regra 5: fechou ou arquivou nesta atualização → refresh das views de BI.
    _schedule_cycle_events(
        previous_cycle_dates, (updated.lawsuit.closure_date, updated.lawsuit.archived_date)
    )
    return _to_response(updated)


@router.post("/{lawsuit_id}/move-stage")
async def move_lawsuit_stage(
    lawsuit_id: uuid.UUID,
    payload: MoveStageRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> MoveStageResponse:
    """Spec 051 — arrastar card no Kanban chama isto (regra 4: otimista na UI, reverte
    se der 403/422). Spec 053, regra 1: devolve a sugestão de workflow da etapa
    destino, se houver — a UI decide se mostra o diálogo de confirmação."""
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)
    board = BoardService(session=session, tenant_id=current_user.tenant_id)
    try:
        await board.move_stage(detail.lawsuit, stage_id=payload.stage_id, actor=current_user)
    except NotResponsibleForLawsuitError as exc:
        raise HTTPException(
            status_code=403, detail="Só o responsável pelo processo pode mover a etapa."
        ) from exc
    except StageNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Etapa não encontrada.") from exc
    updated = await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)

    workflows = LawsuitWorkflowService(session=session, tenant_id=current_user.tenant_id)
    workflow = await workflows.suggest_for_stage_id(updated.lawsuit, payload.stage_id)
    suggested = (
        SuggestedWorkflowResponse(id=workflow.id, name=workflow.name)
        if workflow is not None
        else None
    )
    return MoveStageResponse(lawsuit=_to_response(updated), suggested_workflow=suggested)


@router.post("/{lawsuit_id}/apply-workflow")
async def apply_lawsuit_workflow(
    lawsuit_id: uuid.UUID,
    payload: ApplyWorkflowRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> ApplyWorkflowResponse:
    """Spec 053, regras 2/3/8: preview mora em `POST /workflows/{id}/preview` (spec
    038, mesma resolução) — este endpoint aplica de fato e grava o registro que
    permite desfazer (regra 4)."""
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)
    workflows = LawsuitWorkflowService(session=session, tenant_id=current_user.tenant_id)
    workflow = await get_or_404(
        lambda: workflows.get_workflow(payload.workflow_id),
        "Workflow não encontrado.",
    )
    try:
        outcome = await workflows.apply(
            detail.lawsuit,
            workflow,
            current_user,
            stage_id=payload.stage_id,
            confirm_duplicate=payload.confirm_duplicate,
        )
    except WorkflowAlreadyAppliedError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "Este workflow já foi aplicado neste processo em "
                f"{exc.applied_at.isoformat()}. Confirme para aplicar de novo."
            ),
        ) from exc
    except InactiveAssigneeError as exc:
        raise HTTPException(
            status_code=422, detail="Um responsável configurado está inativo — nada foi criado."
        ) from exc
    return ApplyWorkflowResponse(
        application_id=outcome.application.id,
        created=len(outcome.application.posts_created),
        post_ids=list(outcome.application.posts_created),
        skipped=[
            SkippedWorkflowStepResponse(task_type_name=item.task_type_name, reason=item.reason)
            for item in outcome.skipped
        ],
    )


@router.post("/{lawsuit_id}/suppress-workflow", status_code=204)
async def suppress_lawsuit_workflow(
    lawsuit_id: uuid.UUID,
    payload: SuppressWorkflowRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    """Spec 053, regra 6: "não sugerir novamente" para este processo+etapa."""
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)
    workflows = LawsuitWorkflowService(session=session, tenant_id=current_user.tenant_id)
    await workflows.suppress(lawsuit_id, payload.stage_id)


@router.get("/{lawsuit_id}/workflow-applications")
async def list_lawsuit_workflow_applications(
    lawsuit_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> WorkflowApplicationListResponse:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)
    workflows = LawsuitWorkflowService(session=session, tenant_id=current_user.tenant_id)
    rows = await workflows.list_applications(lawsuit_id)
    return WorkflowApplicationListResponse(
        items=[
            WorkflowApplicationResponse(
                id=application.id,
                workflow_id=application.workflow_id,
                workflow_name=name,
                stage_id=application.stage_id,
                applied_by=application.applied_by,
                posts_created=list(application.posts_created),
                applied_at=application.applied_at,
            )
            for application, name in rows
        ]
    )


@router.delete("/{lawsuit_id}/workflow-applications/{application_id}", status_code=204)
async def undo_lawsuit_workflow_application(
    lawsuit_id: uuid.UUID,
    application_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    """Spec 053, regra 5: desfazer só em até 1 h e só se nenhuma tarefa criada foi
    concluída — remove as tarefas e o próprio registro de aplicação."""
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)
    workflows = LawsuitWorkflowService(session=session, tenant_id=current_user.tenant_id)
    try:
        application = await workflows.get_application(lawsuit_id, application_id)
        await workflows.undo(application)
    except WorkflowApplicationNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Aplicação não encontrada.") from exc
    except WorkflowUndoWindowExpiredError as exc:
        raise HTTPException(
            status_code=409, detail="Desfazer só é possível em até 1 hora após aplicar."
        ) from exc
    except WorkflowUndoHasCompletedTaskError as exc:
        raise HTTPException(
            status_code=409,
            detail="Uma das tarefas criadas já foi concluída — não é possível desfazer.",
        ) from exc


@router.delete("/{lawsuit_id}", status_code=204)
async def delete_lawsuit(
    lawsuit_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    redis: Redis = Depends(get_redis),
    clock: Clock = Depends(get_clock),
) -> None:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)
    was_archived = detail.lawsuit.is_archived
    await service.delete(detail.lawsuit)
    # Soft delete arquiva (is_archived) — o card de ativos muda (regra 7, spec 028).
    await invalidate_stats_cache(
        redis,
        current_user.tenant_id,
        detail.lawsuit.closure_date,
        detail.lawsuit.archived_date,
        today=clock.today(),
    )
    # Spec 078, regra 5: arquivar pelo soft delete também invalida as views de BI.
    if not was_archived:
        schedule_aggregate_refresh("lawsuit.archived")


@router.get("/{lawsuit_id}/financial-summary")
async def get_financial_summary(
    lawsuit_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    _financial: User = Depends(require_financial(FinancialAccess.READ_ONLY)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> FinancialSummaryResponse:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)
    summary = await service.financial_summary(detail.lawsuit)
    return FinancialSummaryResponse(
        case_value=summary.case_value,
        fees_value=summary.fees_value,
        received=summary.received,
        to_receive=summary.to_receive,
        expenses=summary.expenses,
        net_result=summary.net_result,
    )


@router.get("/{lawsuit_id}/timeline")
async def get_timeline(
    lawsuit_id: uuid.UUID,
    kinds: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> TimelineResponse:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    # Spec 098, regra 1: a timeline não mostra grupo nem fase — carregar o detalhe
    # completo só para checar existência custava uma query jogada fora.
    lawsuit = await get_or_404(lambda: service.get_lawsuit(lawsuit_id), _NOT_FOUND_DETAIL)
    # Regra 2: toggles combináveis; `kinds=` vazio (nenhum marcado) → timeline vazia,
    # nunca a lista completa. Omitir o parâmetro traz todos os tipos.
    kind_list = TIMELINE_KINDS if kinds is None else [k for k in kinds.split(",") if k]
    movements = MovementsService(session, current_user.tenant_id)
    page = await movements.list_timeline(
        lawsuit.id, kinds=kind_list, cursor=cursor, limit=min(limit, 100)
    )
    return TimelineResponse(
        items=[
            TimelineItemResponse(
                kind=item.kind,
                id=item.id,
                occurred_at=item.occurred_at,
                title=item.title,
                summary=item.summary,
                actor=item.actor,
                metadata={"header": item.header, "external_code": item.external_code},
            )
            for item in page.items
        ],
        next_cursor=page.next_cursor,
        total=page.total,
    )


@router.post("/{lawsuit_id}/movements", status_code=201)
async def create_movement(
    lawsuit_id: uuid.UUID,
    payload: MovementCreateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> MovementResponse:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)
    movements = MovementsService(session, current_user.tenant_id)
    movement = await movements.create_movement(detail.lawsuit, payload, current_user)
    return _to_movement_response(movement)


async def _get_movement_or_404(
    service: LawsuitService,
    movements: MovementsService,
    lawsuit_id: uuid.UUID,
    movement_id: uuid.UUID,
) -> LawsuitMovement:
    detail = await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)
    movement = await movements.movements.get_by_id(movement_id)
    if movement is None or movement.lawsuit_id != detail.lawsuit.id:
        raise HTTPException(status_code=404, detail="Movimentação não encontrada.")
    return movement


@router.put("/{lawsuit_id}/movements/{movement_id}")
async def update_movement(
    lawsuit_id: uuid.UUID,
    movement_id: uuid.UUID,
    payload: MovementUpdateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> MovementResponse:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    movements = MovementsService(session, current_user.tenant_id)
    movement = await _get_movement_or_404(service, movements, lawsuit_id, movement_id)
    try:
        updated = await movements.update_movement(movement, payload, current_user)
    except TribunalMovementImmutableError as exc:
        raise HTTPException(
            status_code=403, detail="Movimentação do tribunal não pode ser editada."
        ) from exc
    except MovementNotAuthorError as exc:
        raise HTTPException(
            status_code=403,
            detail="Só quem criou a movimentação (ou um administrador) pode editá-la.",
        ) from exc
    return _to_movement_response(updated)


@router.delete("/{lawsuit_id}/movements/{movement_id}", status_code=204)
async def delete_movement(
    lawsuit_id: uuid.UUID,
    movement_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    movements = MovementsService(session, current_user.tenant_id)
    movement = await _get_movement_or_404(service, movements, lawsuit_id, movement_id)
    try:
        await movements.delete_movement(movement, current_user)
    except TribunalMovementImmutableError as exc:
        raise HTTPException(
            status_code=403, detail="Movimentação do tribunal não pode ser excluída."
        ) from exc
    except MovementNotAuthorError as exc:
        raise HTTPException(
            status_code=403,
            detail="Só quem criou a movimentação (ou um administrador) pode excluí-la.",
        ) from exc


@router.get("/{lawsuit_id}/parties")
async def list_parties(
    lawsuit_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> list[PartyResponse]:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)
    parties_service = PartiesService(session, current_user.tenant_id)
    parties = await parties_service.list_parties(detail.lawsuit.id)
    return [_to_party_response(party) for party in parties]


@router.post("/{lawsuit_id}/parties", status_code=201)
async def add_party(
    lawsuit_id: uuid.UUID,
    payload: PartyCreateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PartyResponse:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)
    parties_service = PartiesService(session, current_user.tenant_id)
    try:
        party = await parties_service.add_party(detail.lawsuit, payload)
    except (PartyCustomerNotFoundError, DuplicatePartyError) as exc:
        _raise_party_errors(exc)
    return _to_party_response(party)


async def _get_party_or_404(
    service: LawsuitService,
    parties_service: PartiesService,
    lawsuit_id: uuid.UUID,
    party_id: uuid.UUID,
) -> PartyDetail:
    detail = await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)
    party = await parties_service.parties.get_by_id(party_id)
    if party is None or party.lawsuit_id != detail.lawsuit.id:
        raise HTTPException(status_code=404, detail=_PARTY_NOT_FOUND_DETAIL)
    customer = await parties_service.customers.get_by_id(party.customer_id)
    if customer is None:
        # FK garante que o contato existe; None aqui só aconteceria com RLS mal aplicado.
        raise HTTPException(status_code=404, detail=_PARTY_NOT_FOUND_DETAIL)
    return PartyDetail(party=party, customer_name=customer.name)


@router.put("/{lawsuit_id}/parties/{party_id}")
async def update_party(
    lawsuit_id: uuid.UUID,
    party_id: uuid.UUID,
    payload: PartyUpdateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PartyResponse:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    parties_service = PartiesService(session, current_user.tenant_id)
    detail = await _get_party_or_404(service, parties_service, lawsuit_id, party_id)
    try:
        updated = await parties_service.update_party(detail.party, payload)
    except (PartyCustomerNotFoundError, DuplicatePartyError) as exc:
        _raise_party_errors(exc)
    return _to_party_response(updated)


@router.delete("/{lawsuit_id}/parties/{party_id}", status_code=204)
async def remove_party(
    lawsuit_id: uuid.UUID,
    party_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    parties_service = PartiesService(session, current_user.tenant_id)
    detail = await _get_party_or_404(service, parties_service, lawsuit_id, party_id)
    try:
        await parties_service.remove_party(detail.party)
    except LastPartyError as exc:
        raise HTTPException(status_code=409, detail=_LAST_PARTY_DETAIL) from exc


def _to_sync_status_response(lawsuit: Lawsuit, *, is_syncing: bool) -> SyncStatusResponse:
    return SyncStatusResponse(
        last_sync_at=lawsuit.datajud_last_sync_at,
        last_update=lawsuit.datajud_last_update,
        not_found_count=lawsuit.datajud_not_found_count,
        is_syncing=is_syncing,
    )


@router.get("/{lawsuit_id}/sync-status")
async def get_sync_status(
    lawsuit_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    redis: Redis = Depends(get_redis),
) -> SyncStatusResponse:
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)
    is_syncing = bool(await redis.exists(sync_lock_key(lawsuit_id)))
    return _to_sync_status_response(detail.lawsuit, is_syncing=is_syncing)


@router.get("/{lawsuit_id}/sync-runs")
async def list_sync_runs(
    lawsuit_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> SyncRunListResponse:
    """Spec 050, alvo 1: histórico de execução do DataJud — mesma `sync_runs`
    do DJEN (spec 043), agora também pelo lado `lawsuit_id`."""
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)
    runs = await LawsuitSyncRunService(session).list_for_lawsuit(lawsuit_id)
    return SyncRunListResponse(
        items=[
            SyncRunResponse(
                id=run.id,
                started_at=run.started_at,
                finished_at=run.finished_at,
                found_count=run.found_count,
                new_count=run.new_count,
                error=run.error,
            )
            for run in runs
        ]
    )


@router.post("/{lawsuit_id}/sync-movements")
async def sync_movements(
    lawsuit_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    redis: Redis = Depends(get_redis),
) -> SyncMovementsResponse:
    """Gatilho manual (spec 047, §6) — roda a sincronização de UM processo dentro
    da própria request (diferente do lote agendado, que é sempre assíncrono)."""
    service = LawsuitService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(lambda: service.get(lawsuit_id), _NOT_FOUND_DETAIL)

    settings = get_settings()
    http = create_http_client(
        redis=redis,
        policies={
            _DATAJUD_HOST: HostPolicy(rate_limit_per_minute=settings.datajud_rate_limit_per_minute)
        },
    )
    try:
        try:
            client = DatajudClient(
                http=http,
                base_url=settings.datajud_base_url,
                api_key=settings.datajud_api_key or "",
            )
        except DatajudConfigError as exc:
            raise HTTPException(
                status_code=503, detail="DataJud não está configurado (DATAJUD_API_KEY ausente)."
            ) from exc

        datajud_service = DatajudService(session, client)
        sync_service = MovementSyncService(session, current_user.tenant_id, datajud_service)
        lock = RedisSyncLock(redis)
        try:
            result = await sync_service.sync_lawsuit_locked(detail.lawsuit, lock)
        except LawsuitSyncInProgressError as exc:
            raise HTTPException(
                status_code=409,
                detail="Já existe uma sincronização em andamento para este processo.",
            ) from exc
        except DatajudUnauthorizedError as exc:
            raise HTTPException(
                status_code=503,
                detail="Chave pública do DataJud inválida ou rotacionada — veja os alertas.",
            ) from exc
    finally:
        await http.aclose()

    return SyncMovementsResponse(
        status=result.status,
        new_movements=result.new_movements,
        last_sync_at=detail.lawsuit.datajud_last_sync_at,
        last_update=detail.lawsuit.datajud_last_update,
        not_found_count=detail.lawsuit.datajud_not_found_count,
    )
