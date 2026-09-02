import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_file_storage
from app.core.permissions import UserRole, require_role
from app.domain.account.schemas import AccountStorageResponse
from app.domain.auth.deps import get_session_for_current_user
from app.domain.documents.exceptions import (
    DocumentFolderNotFoundError,
    DocumentNotFoundError,
    DocumentScopeNotFoundError,
    DuplicateFolderNameError,
    FolderScopeMismatchError,
)
from app.domain.documents.models import Document, DocumentFolder, DocumentScopeType
from app.domain.documents.schemas import (
    DocumentFolderCreateRequest,
    DocumentFolderResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentSearchResponse,
    SortField,
    SortOrder,
    UploadResultResponse,
)
from app.domain.documents.service import DocumentService
from app.domain.users.models import User
from app.integrations.storage.base import FileStorage

router = APIRouter(tags=["documents"])

_SCOPE_NOT_FOUND_DETAIL = "Contato ou processo não encontrado."
_FOLDER_NOT_FOUND_DETAIL = "Pasta não encontrada."
_DOCUMENT_NOT_FOUND_DETAIL = "Documento não encontrado."


def _folder_to_response(folder: DocumentFolder) -> DocumentFolderResponse:
    return DocumentFolderResponse(
        id=folder.id,
        scope_type=folder.scope_type,
        scope_id=folder.scope_id,
        parent_folder_id=folder.parent_folder_id,
        name=folder.name,
        created_by=folder.created_by,
        created_at=folder.created_at,
    )


def _document_to_response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        scope_type=document.scope_type,
        scope_id=document.scope_id,
        folder_id=document.folder_id,
        filename=document.filename,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        uploaded_by=document.uploaded_by,
        created_at=document.created_at,
    )


def _service(session: AsyncSession, storage: FileStorage, current_user: User) -> DocumentService:
    return DocumentService(session=session, storage=storage, tenant_id=current_user.tenant_id)


@router.get("/documents")
async def list_documents(
    scope_type: DocumentScopeType = Query(),
    scope_id: uuid.UUID = Query(),
    folder_id: uuid.UUID | None = Query(default=None),
    sort: SortField = Query(default="name"),
    order: SortOrder = Query(default="asc"),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> DocumentListResponse:
    service = _service(session, storage, current_user)
    try:
        folders, documents = await service.list_contents(
            scope_type=scope_type, scope_id=scope_id, folder_id=folder_id, sort=sort, order=order
        )
    except DocumentScopeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_SCOPE_NOT_FOUND_DETAIL) from exc
    except DocumentFolderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_FOLDER_NOT_FOUND_DETAIL) from exc
    except FolderScopeMismatchError as exc:
        raise HTTPException(status_code=404, detail=_FOLDER_NOT_FOUND_DETAIL) from exc
    return DocumentListResponse(
        folders=[_folder_to_response(item) for item in folders],
        documents=[_document_to_response(item) for item in documents],
    )


@router.get("/documents/search")
async def search_documents(
    scope_type: DocumentScopeType = Query(),
    scope_id: uuid.UUID = Query(),
    q: str = Query(min_length=1),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> DocumentSearchResponse:
    service = _service(session, storage, current_user)
    try:
        documents = await service.search(scope_type=scope_type, scope_id=scope_id, query=q)
    except DocumentScopeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_SCOPE_NOT_FOUND_DETAIL) from exc
    return DocumentSearchResponse(documents=[_document_to_response(item) for item in documents])


@router.post("/documents", status_code=201)
async def upload_documents(
    files: list[UploadFile],
    scope_type: Annotated[DocumentScopeType, Form()],
    scope_id: Annotated[uuid.UUID, Form()],
    folder_id: Annotated[uuid.UUID | None, Form()] = None,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> list[UploadResultResponse]:
    service = _service(session, storage, current_user)
    payload: list[tuple[str, str, bytes]] = [
        (
            file.filename or "arquivo",
            file.content_type or "application/octet-stream",
            await file.read(),
        )
        for file in files
    ]
    try:
        results = await service.upload_many(
            current_user,
            scope_type=scope_type,
            scope_id=scope_id,
            folder_id=folder_id,
            files=payload,
        )
    except DocumentScopeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_SCOPE_NOT_FOUND_DETAIL) from exc
    except DocumentFolderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_FOLDER_NOT_FOUND_DETAIL) from exc
    except FolderScopeMismatchError as exc:
        raise HTTPException(status_code=404, detail=_FOLDER_NOT_FOUND_DETAIL) from exc
    return [
        UploadResultResponse(
            filename=result.filename,
            status=result.status,
            document=_document_to_response(result.document) if result.document else None,
            error=result.error,
        )
        for result in results
    ]


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> dict[str, str]:
    service = _service(session, storage, current_user)
    try:
        url = await service.download_url(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_DOCUMENT_NOT_FOUND_DETAIL) from exc
    return {"url": url}


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> None:
    service = _service(session, storage, current_user)
    try:
        await service.delete_document(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_DOCUMENT_NOT_FOUND_DETAIL) from exc


@router.post("/document-folders", status_code=201)
async def create_document_folder(
    payload: DocumentFolderCreateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> DocumentFolderResponse:
    service = _service(session, storage, current_user)
    try:
        folder = await service.create_folder(
            current_user,
            scope_type=payload.scope_type,
            scope_id=payload.scope_id,
            parent_folder_id=payload.parent_folder_id,
            name=payload.name,
        )
    except DocumentScopeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_SCOPE_NOT_FOUND_DETAIL) from exc
    except DocumentFolderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_FOLDER_NOT_FOUND_DETAIL) from exc
    except FolderScopeMismatchError as exc:
        raise HTTPException(status_code=404, detail=_FOLDER_NOT_FOUND_DETAIL) from exc
    except DuplicateFolderNameError as exc:
        raise HTTPException(
            status_code=409, detail="Já existe uma pasta com esse nome aqui."
        ) from exc
    return _folder_to_response(folder)


@router.delete("/document-folders/{folder_id}", status_code=204)
async def delete_document_folder(
    folder_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> None:
    service = _service(session, storage, current_user)
    try:
        await service.delete_folder(folder_id)
    except DocumentFolderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_FOLDER_NOT_FOUND_DETAIL) from exc


@router.get("/account/storage")
async def get_account_storage(
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    storage: FileStorage = Depends(get_file_storage),
) -> AccountStorageResponse:
    """Endpoint mora aqui, não em `account/router.py`: a quota é conceito do domínio
    de documentos (spec 063), e `documents` já depende de `account` (para ler o
    plano) — o inverso criaria import circular entre os dois domínios."""
    service = _service(session, storage, current_user)
    used, quota, plan = await service.storage_usage()
    return AccountStorageResponse(used_bytes=used, quota_bytes=quota, plan=plan)
