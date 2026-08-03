import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_file_storage
from app.core.permissions import UserRole, require_role
from app.domain.attachments.models import Attachment
from app.domain.attachments.rules import AttachmentTooLargeError, AttachmentTypeBlockedError
from app.domain.attachments.service import (
    AttachmentDeleteForbiddenError,
    AttachmentNotFoundError,
    AttachmentResponse,
    AttachmentService,
    AttachmentTargetNotFoundError,
)
from app.domain.auth.deps import get_session_for_current_user
from app.domain.users.models import User
from app.integrations.storage.base import FileStorage

router = APIRouter(tags=["attachments"])

_NOT_FOUND_DETAIL = "Anexo não encontrado."


def _to_response(attachment: Attachment) -> AttachmentResponse:
    return AttachmentResponse(
        id=attachment.id,
        filename=attachment.filename,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        attached_to_type=attachment.attached_to_type,
        attached_to_id=attachment.attached_to_id,
        uploaded_by=attachment.uploaded_by,
        created_at=attachment.created_at,
    )


@router.post("/attachments", status_code=201)
async def upload_attachment(
    file: UploadFile,
    attached_to_type: Annotated[str, Form()],
    attached_to_id: Annotated[uuid.UUID, Form()],
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> AttachmentResponse:
    service = AttachmentService(session=session, storage=storage, tenant_id=current_user.tenant_id)
    content = await file.read()
    try:
        attachment = await service.upload(
            current_user,
            attached_to_type=attached_to_type,
            attached_to_id=attached_to_id,
            filename=file.filename or "arquivo",
            content_type=file.content_type or "application/octet-stream",
            content=content,
        )
    except AttachmentTooLargeError as exc:
        raise HTTPException(status_code=422, detail="Anexo acima de 50 MB.") from exc
    except AttachmentTypeBlockedError as exc:
        raise HTTPException(status_code=422, detail="Tipo de arquivo não permitido.") from exc
    except AttachmentTargetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Alvo do anexo não encontrado.") from exc
    return _to_response(attachment)


@router.get("/attachments")
async def list_attachments(
    attached_to_type: str = Query(),
    attached_to_id: uuid.UUID = Query(),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> list[AttachmentResponse]:
    service = AttachmentService(session=session, storage=storage, tenant_id=current_user.tenant_id)
    try:
        items = await service.list_for(attached_to_type, attached_to_id, current_user)
    except AttachmentTargetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Alvo do anexo não encontrado.") from exc
    return [_to_response(item) for item in items]


@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> dict[str, str]:
    service = AttachmentService(session=session, storage=storage, tenant_id=current_user.tenant_id)
    try:
        url = await service.download_url(attachment_id, current_user)
    except AttachmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL) from exc
    return {"url": url}


@router.delete("/attachments/{attachment_id}", status_code=204)
async def delete_attachment(
    attachment_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> None:
    service = AttachmentService(session=session, storage=storage, tenant_id=current_user.tenant_id)
    try:
        await service.delete(attachment_id, current_user)
    except AttachmentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL) from exc
    except AttachmentDeleteForbiddenError as exc:
        raise HTTPException(
            status_code=403, detail="Só quem enviou (ou um administrador) pode remover o anexo."
        ) from exc
