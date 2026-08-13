import uuid
from datetime import datetime

from pydantic import BaseModel

from app.domain.documents.models import DocumentScopeType


class DocumentFolderCreateRequest(BaseModel):
    scope_type: DocumentScopeType
    scope_id: uuid.UUID
    parent_folder_id: uuid.UUID | None = None
    name: str


class DocumentFolderResponse(BaseModel):
    id: uuid.UUID
    scope_type: DocumentScopeType
    scope_id: uuid.UUID
    parent_folder_id: uuid.UUID | None
    name: str
    created_by: uuid.UUID
    created_at: datetime


class DocumentResponse(BaseModel):
    id: uuid.UUID
    scope_type: DocumentScopeType
    scope_id: uuid.UUID
    folder_id: uuid.UUID | None
    filename: str
    content_type: str
    size_bytes: int
    uploaded_by: uuid.UUID
    created_at: datetime


class DocumentListResponse(BaseModel):
    folders: list[DocumentFolderResponse]
    documents: list[DocumentResponse]


class DocumentSearchResponse(BaseModel):
    documents: list[DocumentResponse]


class UploadResultResponse(BaseModel):
    filename: str
    status: str
    document: DocumentResponse | None = None
    error: str | None = None
