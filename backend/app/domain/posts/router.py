import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http import get_or_404
from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.posts.exceptions import (
    AssigneeNotActiveError,
    DuplicatePostError,
    LawsuitNotFoundError,
    SquadNotFoundError,
    TaskTypeNotFoundError,
)
from app.domain.posts.schemas import (
    AssigneeResponse,
    PostCreateRequest,
    PostResponse,
    PostUpdateRequest,
)
from app.domain.posts.service import PostDetail, PostService
from app.domain.users.models import User

router = APIRouter(tags=["posts"])

_NOT_FOUND_DETAIL = "Tarefa não encontrada."
_LAWSUIT_NOT_FOUND_DETAIL = "Processo não encontrado."


def _to_response(detail: PostDetail) -> PostResponse:
    post = detail.post
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
        assignees=[AssigneeResponse(id=user.id, name=user.name) for user in detail.assignees],
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
    detail = await get_or_404(lambda: service.get(post_id), _NOT_FOUND_DETAIL)
    return _to_response(detail)


@router.put("/posts/{post_id}")
async def update_post(
    post_id: uuid.UUID,
    payload: PostUpdateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> PostResponse:
    service = PostService(session=session, tenant_id=current_user.tenant_id)
    detail = await get_or_404(lambda: service.get(post_id), _NOT_FOUND_DETAIL)
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
    detail = await get_or_404(lambda: service.get(post_id), _NOT_FOUND_DETAIL)
    await service.delete(detail.post)


@router.get("/lawsuits/{lawsuit_id}/posts")
async def list_lawsuit_posts(
    lawsuit_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> list[PostResponse]:
    service = PostService(session=session, tenant_id=current_user.tenant_id)
    details = await service.list_for_lawsuit(lawsuit_id)
    return [_to_response(detail) for detail in details]
