import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http import get_or_404
from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.posts.exceptions import (
    AssigneeNotActiveError,
    CompleteForOthersForbiddenError,
    DuplicatePostError,
    FutureCompletionError,
    LawsuitNotFoundError,
    NotAssigneeError,
    SquadNotFoundError,
    TaskTypeNotFoundError,
)
from app.domain.posts.models import PostRecurrence
from app.domain.posts.recurrence_service import RecurrenceService
from app.domain.posts.schemas import (
    AssigneeResponse,
    PostCompleteRequest,
    PostCreateRequest,
    PostFlagsRequest,
    PostFlagValueRequest,
    PostReopenRequest,
    PostResponse,
    PostUpdateRequest,
    RecurrencePreviewResponse,
    RecurrenceResponse,
    RecurrenceUpdateRequest,
)
from app.domain.posts.service import PostDetail, PostService
from app.domain.users.models import User
from app.workers.scores import schedule_scores_refresh

router = APIRouter(tags=["posts"])

_NOT_FOUND_DETAIL = "Tarefa não encontrada."
_LAWSUIT_NOT_FOUND_DETAIL = "Processo não encontrado."
_NOT_ASSIGNEE_DETAIL = "Só um responsável pela tarefa pode executar esta ação."
_NO_RECURRENCE_DETAIL = "A tarefa não pertence a uma série de recorrência."


def _to_recurrence_response(recurrence: PostRecurrence) -> RecurrenceResponse:
    return RecurrenceResponse(
        id=recurrence.id,
        template_post_id=recurrence.template_post_id,
        period=recurrence.period,
        repeat_on=recurrence.repeat_on,
        until_date=recurrence.until_date,
        max_occurrences=recurrence.max_occurrences,
        occurrences_created=recurrence.occurrences_created,
        last_generated_date=recurrence.last_generated_date,
        is_active=recurrence.is_active,
        created_at=recurrence.created_at,
    )


def _to_response(detail: PostDetail) -> PostResponse:
    post = detail.post
    if detail.redacted:
        # Regra 8: presença sem conteúdo — o não envolvido vê que existe uma tarefa
        # privada (metadados de existência), nada mais.
        return PostResponse(
            id=post.id,
            lawsuit_id=post.lawsuit_id,
            task_type_id=None,
            task_type_name="Tarefa privada",
            created_by=None,
            scheduled_date=None,
            scheduled_time=None,
            end_date=None,
            end_time=None,
            deadline_date=None,
            all_day=False,
            location=None,
            comments=None,
            reward_snapshot=0,
            is_important=False,
            is_urgent=False,
            is_future=False,
            is_private=True,
            show_in_schedule=False,
            all_completed=False,
            recurrence_id=None,
            redacted=True,
            assignees=[],
            created_at=post.created_at,
            updated_at=post.updated_at,
        )
    return PostResponse(
        id=post.id,
        lawsuit_id=post.lawsuit_id,
        task_type_id=post.task_type_id,
        task_type_name=detail.task_type_name,
        created_by=post.created_by,
        scheduled_date=post.scheduled_date,
        scheduled_time=post.scheduled_time,
        end_date=post.end_date,
        end_time=post.end_time,
        deadline_date=post.deadline_date,
        all_day=post.all_day,
        location=post.location,
        comments=post.comments,
        reward_snapshot=post.reward_snapshot,
        is_important=post.is_important,
        is_urgent=post.is_urgent,
        is_future=post.is_future,
        is_private=post.is_private,
        show_in_schedule=post.show_in_schedule,
        # Regra 3: concluída como um todo quando TODOS os responsáveis concluíram.
        all_completed=all(item.line.completed_at is not None for item in detail.assignees),
        recurrence_id=post.recurrence_id,
        assignees=[
            AssigneeResponse(
                id=item.user.id,
                name=item.user.name,
                completed_at=item.line.completed_at,
                points_earned=item.line.points_earned,
                completed_by=item.line.completed_by,
                is_read=item.line.is_read,
                is_starred=item.line.is_starred,
            )
            for item in detail.assignees
        ],
        created_at=post.created_at,
        updated_at=post.updated_at,
    )


def _raise_reference_errors(exc: Exception) -> None:
    if isinstance(exc, LawsuitNotFoundError):
        raise HTTPException(status_code=422, detail=_LAWSUIT_NOT_FOUND_DETAIL) from exc
    if isinstance(exc, TaskTypeNotFoundError):
        raise HTTPException(status_code=422, detail="Tipo de tarefa não encontrado.") from exc
    if isinstance(exc, SquadNotFoundError):
        raise HTTPException(status_code=422, detail="Time não encontrado.") from exc
    if isinstance(exc, AssigneeNotActiveError):
        raise HTTPException(
            status_code=422,
            detail="Responsável precisa ser um usuário ativo do tenant (mínimo 1).",
        ) from exc
    raise exc


@router.post("/posts", status_code=201)
async def create_post(
    payload: PostCreateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PostResponse:
    service = PostService(session=session, tenant_id=current_user.tenant_id)
    try:
        created = await service.create(payload, current_user)
    except DuplicatePostError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "detail": "Já existe uma tarefa igual (processo, tipo, data e responsáveis).",
                "existing_id": str(exc.existing_id),
            },
        ) from exc
    except (
        LawsuitNotFoundError,
        TaskTypeNotFoundError,
        SquadNotFoundError,
        AssigneeNotActiveError,
    ) as exc:
        _raise_reference_errors(exc)
    return _to_response(created)


@router.get("/posts/{post_id}")
async def get_post(
    post_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PostResponse:
    service = PostService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(
        lambda: service.get(post_id, viewer_id=current_user.id), _NOT_FOUND_DETAIL
    )
    return _to_response(detail)


@router.put("/posts/{post_id}")
async def update_post(
    post_id: uuid.UUID,
    payload: PostUpdateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PostResponse:
    service = PostService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(
        lambda: service.get(post_id, viewer_id=current_user.id), _NOT_FOUND_DETAIL
    )
    try:
        updated = await service.update(detail.post, payload)
    except (
        LawsuitNotFoundError,
        TaskTypeNotFoundError,
        SquadNotFoundError,
        AssigneeNotActiveError,
    ) as exc:
        _raise_reference_errors(exc)
    return _to_response(updated)


@router.delete("/posts/{post_id}", status_code=204)
async def delete_post(
    post_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    service = PostService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(
        lambda: service.get(post_id, viewer_id=current_user.id), _NOT_FOUND_DETAIL
    )
    await service.delete(detail.post)


@router.put("/posts/{post_id}/flags")
async def update_post_flags(
    post_id: uuid.UUID,
    payload: PostFlagsRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PostResponse:
    service = PostService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(
        lambda: service.get(post_id, viewer_id=current_user.id), _NOT_FOUND_DETAIL
    )
    updated = await service.update_flags(detail.post, payload)
    return _to_response(updated)


@router.post("/posts/{post_id}/complete")
async def complete_post(
    post_id: uuid.UUID,
    payload: PostCompleteRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PostResponse:
    service = PostService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(
        lambda: service.get(post_id, viewer_id=current_user.id), _NOT_FOUND_DETAIL
    )
    try:
        completed = await service.complete(detail.post, current_user, payload)
    except NotAssigneeError as exc:
        raise HTTPException(status_code=403, detail=_NOT_ASSIGNEE_DETAIL) from exc
    except CompleteForOthersForbiddenError as exc:
        raise HTTPException(
            status_code=403,
            detail="Concluir pela linha de outro responsável exige perfil ADMINISTRADOR.",
        ) from exc
    except FutureCompletionError as exc:
        raise HTTPException(
            status_code=422, detail="A conclusão não pode ser uma data futura."
        ) from exc
    # Spec 039, regra 9: concluir agenda o refresh imediato da view de pontuação
    # (countdown curto — o commit desta request acontece no teardown da sessão, logo
    # após o retorno). Broker fora não afeta a conclusão; o beat de 15 min cobre.
    schedule_scores_refresh()
    return _to_response(completed)


@router.post("/posts/{post_id}/reopen")
async def reopen_post(
    post_id: uuid.UUID,
    payload: PostReopenRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PostResponse:
    service = PostService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(
        lambda: service.get(post_id, viewer_id=current_user.id), _NOT_FOUND_DETAIL
    )
    try:
        reopened = await service.reopen(detail.post, current_user, payload)
    except NotAssigneeError as exc:
        raise HTTPException(status_code=403, detail=_NOT_ASSIGNEE_DETAIL) from exc
    except CompleteForOthersForbiddenError as exc:
        raise HTTPException(
            status_code=403,
            detail="Reabrir pela linha de outro responsável exige perfil ADMINISTRADOR.",
        ) from exc
    # Reabrir também muda a pontuação — mesmo refresh da regra 9 (spec 039).
    schedule_scores_refresh()
    return _to_response(reopened)


@router.post("/posts/{post_id}/read")
async def read_post(
    post_id: uuid.UUID,
    payload: PostFlagValueRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PostResponse:
    service = PostService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(
        lambda: service.get(post_id, viewer_id=current_user.id), _NOT_FOUND_DETAIL
    )
    try:
        updated = await service.set_read(detail.post, current_user, value=payload.value)
    except NotAssigneeError as exc:
        raise HTTPException(status_code=403, detail=_NOT_ASSIGNEE_DETAIL) from exc
    return _to_response(updated)


@router.post("/posts/{post_id}/star")
async def star_post(
    post_id: uuid.UUID,
    payload: PostFlagValueRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PostResponse:
    service = PostService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(
        lambda: service.get(post_id, viewer_id=current_user.id), _NOT_FOUND_DETAIL
    )
    try:
        updated = await service.set_starred(detail.post, current_user, value=payload.value)
    except NotAssigneeError as exc:
        raise HTTPException(status_code=403, detail=_NOT_ASSIGNEE_DETAIL) from exc
    return _to_response(updated)


@router.get("/lawsuits/{lawsuit_id}/posts")
async def list_lawsuit_posts(
    lawsuit_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> list[PostResponse]:
    service = PostService(session=session, tenant_id=current_user.tenant_id)
    details = await service.list_for_lawsuit(lawsuit_id, viewer_id=current_user.id)
    return [_to_response(detail) for detail in details]


async def _resolve_recurrence(
    post_id: uuid.UUID,
    current_user: User,
    session: AsyncSession,
) -> tuple[PostDetail, PostRecurrence]:
    """Post + série dele, com 404 nos dois saltos (post inexistente/privado; tarefa
    avulsa sem série)."""
    service = PostService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(
        lambda: service.get(post_id, viewer_id=current_user.id), _NOT_FOUND_DETAIL
    )
    recurrence = await service.recurrences.get_for_post(detail.post)
    if recurrence is None:
        raise HTTPException(status_code=404, detail=_NO_RECURRENCE_DETAIL)
    return detail, recurrence


@router.get("/posts/{post_id}/recurrence")
async def get_recurrence(
    post_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> RecurrenceResponse:
    _detail, recurrence = await _resolve_recurrence(post_id, current_user, session)
    return _to_recurrence_response(recurrence)


@router.put("/posts/{post_id}/recurrence")
async def update_recurrence(
    post_id: uuid.UUID,
    payload: RecurrenceUpdateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> RecurrenceResponse:
    _detail, recurrence = await _resolve_recurrence(post_id, current_user, session)
    service = RecurrenceService(session=session, tenant_id=current_user.tenant_id)
    # Regra 8: a edição vale para as ocorrências futuras — as já geradas ficam como
    # estão (o service não toca em occurrences_created nem em last_generated_date).
    updated = await service.update_series(recurrence, payload)
    return _to_recurrence_response(updated)


@router.delete("/posts/{post_id}/recurrence", status_code=204)
async def delete_recurrence(
    post_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    _detail, recurrence = await _resolve_recurrence(post_id, current_user, session)
    service = RecurrenceService(session=session, tenant_id=current_user.tenant_id)
    # Regra 7: encerrar a série preserva as ocorrências já geradas.
    await service.deactivate(recurrence)


@router.get("/posts/{post_id}/recurrence/preview")
async def preview_recurrence(
    post_id: uuid.UUID,
    count: int = Query(default=5, ge=1, le=50),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> RecurrencePreviewResponse:
    _detail, recurrence = await _resolve_recurrence(post_id, current_user, session)
    service = RecurrenceService(session=session, tenant_id=current_user.tenant_id)
    dates = await service.preview(recurrence, count=count)
    return RecurrencePreviewResponse(dates=dates)
