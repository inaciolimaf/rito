import uuid

from fastapi import APIRouter, Depends, HTTPException
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
from app.domain.posts.schemas import (
    AssigneeResponse,
    PostCompleteRequest,
    PostCreateRequest,
    PostFlagsRequest,
    PostFlagValueRequest,
    PostReopenRequest,
    PostResponse,
    PostUpdateRequest,
)
from app.domain.posts.service import PostDetail, PostService
from app.domain.users.models import User

router = APIRouter(tags=["posts"])

_NOT_FOUND_DETAIL = "Tarefa não encontrada."
_LAWSUIT_NOT_FOUND_DETAIL = "Processo não encontrado."
_NOT_ASSIGNEE_DETAIL = "Só um responsável pela tarefa pode executar esta ação."


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
