import base64
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_file_storage
from app.core.permissions import UserRole, require_role
from app.domain.attachments.service import AttachmentResponse
from app.domain.auth.deps import get_session_for_current_user
from app.domain.comments.service import (
    CommentDetail,
    CommentEditForbiddenError,
    CommentNotFoundError,
    CommentService,
    PostNotFoundError,
)
from app.domain.users.models import User
from app.integrations.storage.base import FileStorage

router = APIRouter(tags=["comments"])

_SEPARATOR = "\x1f"


class CommentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=10000)


class CommentAuthorResponse(BaseModel):
    id: uuid.UUID
    name: str


class CommentResponse(BaseModel):
    id: uuid.UUID
    post_id: uuid.UUID
    author: CommentAuthorResponse
    # Regra 4: comentário removido volta com body=None e deleted=true — a UI mostra
    # "comentário removido" preservando o lugar na thread.
    body: str | None
    mentioned_user_ids: list[uuid.UUID]
    attachments: list[AttachmentResponse]
    deleted: bool
    created_at: datetime
    updated_at: datetime


class CommentPage(BaseModel):
    """Contrato de listagem do CLAUDE.md §6 — keyset, nunca offset."""

    items: list[CommentResponse]
    next_cursor: str | None
    total: int


def _encode_cursor(detail: CommentDetail) -> str:
    comment = detail.comment
    raw = f"{comment.created_at.isoformat()}{_SEPARATOR}{comment.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    value, _, id_str = raw.rpartition(_SEPARATOR)
    return datetime.fromisoformat(value), uuid.UUID(id_str)


def _to_response(detail: CommentDetail) -> CommentResponse:
    comment = detail.comment
    deleted = comment.deleted_at is not None
    return CommentResponse(
        id=comment.id,
        post_id=comment.post_id,
        author=CommentAuthorResponse(id=comment.author_id, name=detail.author_name),
        body=None if deleted else comment.body,
        mentioned_user_ids=[] if deleted else list(comment.mentioned_user_ids),
        attachments=[
            AttachmentResponse(
                id=attachment.id,
                filename=attachment.filename,
                content_type=attachment.content_type,
                size_bytes=attachment.size_bytes,
                attached_to_type=attachment.attached_to_type,
                attached_to_id=attachment.attached_to_id,
                uploaded_by=attachment.uploaded_by,
                created_at=attachment.created_at,
            )
            for attachment in detail.attachments
        ],
        deleted=deleted,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )


def _service(session: AsyncSession, storage: FileStorage, user: User) -> CommentService:
    return CommentService(session=session, storage=storage, tenant_id=user.tenant_id)


@router.post("/posts/{post_id}/comments", status_code=201)
async def create_comment(
    post_id: uuid.UUID,
    payload: CommentCreateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> CommentResponse:
    service = _service(session, storage, current_user)
    try:
        detail = await service.create(post_id, current_user, payload.body)
    except PostNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.") from exc
    return _to_response(detail)


@router.get("/posts/{post_id}/comments")
async def list_comments(
    post_id: uuid.UUID,
    cursor: str | None = Query(default=None),
    # Regra 10: thread crescente paginada a partir de 50.
    limit: int = Query(default=50, ge=1, le=50),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> CommentPage:
    service = _service(session, storage, current_user)
    try:
        items, total, has_more = await service.list_for_post(
            post_id,
            current_user.id,
            cursor=_decode_cursor(cursor) if cursor else None,
            limit=limit,
        )
    except PostNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.") from exc
    return CommentPage(
        items=[_to_response(item) for item in items],
        next_cursor=_encode_cursor(items[-1]) if has_more and items else None,
        total=total,
    )


@router.put("/comments/{comment_id}")
async def update_comment(
    comment_id: uuid.UUID,
    payload: CommentCreateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> CommentResponse:
    service = _service(session, storage, current_user)
    try:
        detail = await service.update(comment_id, current_user, payload.body)
    except CommentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Comentário não encontrado.") from exc
    except CommentEditForbiddenError as exc:
        raise HTTPException(
            status_code=403,
            detail="A edição é do autor em até 15 minutos; depois, só um administrador.",
        ) from exc
    return _to_response(detail)


@router.delete("/comments/{comment_id}", status_code=204)
async def delete_comment(
    comment_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> None:
    service = _service(session, storage, current_user)
    try:
        await service.delete(comment_id, current_user)
    except CommentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Comentário não encontrado.") from exc
    except CommentEditForbiddenError as exc:
        raise HTTPException(
            status_code=403,
            detail="A exclusão é do autor em até 15 minutos; depois, só um administrador.",
        ) from exc
