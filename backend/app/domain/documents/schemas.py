import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

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


class ExtractionFieldResponse(BaseModel):
    """Um campo extraído (spec 091, regras 3 e 4).

    `prefill` é decisão do servidor: abaixo de 0,7 de confiança o campo aparece
    destacado e vazio. `is_valid` é falso quando o CPF, o CNPJ ou o CEP não fecham —
    e mesmo assim o valor vem junto, porque quase sempre é erro de OCR que o humano
    corrige em dois toques.
    """

    value: str
    confidence: float
    prefill: bool
    is_valid: bool


class ExtractionDuplicateResponse(BaseModel):
    customer_id: uuid.UUID
    name: str
    identification: str | None


class ExtractionResponse(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    page_count: int | None
    document_kind: str | None
    target_type: str | None
    used_ocr: bool
    ocr_text: str | None
    fields: dict[str, ExtractionFieldResponse]
    status: str
    action_id: uuid.UUID | None
    applied_id: uuid.UUID | None
    model: str | None
    tokens_used: int | None
    created_at: datetime
    duplicate: ExtractionDuplicateResponse | None = None


class ExtractionApplyRequest(BaseModel):
    """`arguments` é o que vai para a ferramenta de escrita da 084 — os campos já
    corrigidos pela pessoa. `corrections` é o mesmo conjunto visto de outro ângulo: o que
    ela mudou em relação ao que o modelo leu (regra 6)."""

    target_type: str
    arguments: dict[str, Any]
    corrections: dict[str, Any] = Field(default_factory=dict)
