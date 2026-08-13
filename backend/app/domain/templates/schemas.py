import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.domain.templates.models import TemplateType


class TemplateCreateRequest(BaseModel):
    name: str
    type: TemplateType
    content: str = ""
    header_content: str = ""
    footer_content: str = ""
    watermark_text: str | None = None


class TemplateUpdateRequest(BaseModel):
    name: str
    type: TemplateType
    content: str = ""
    header_content: str = ""
    footer_content: str = ""
    watermark_text: str | None = None


class TemplateResponse(BaseModel):
    id: uuid.UUID
    name: str
    type: TemplateType
    content: str
    header_content: str
    footer_content: str
    watermark_text: str | None
    created_by: uuid.UUID
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TemplateListResponse(BaseModel):
    items: list[TemplateResponse]
    next_cursor: str | None
    total: int


class ResolveTemplateRequest(BaseModel):
    customer_id: uuid.UUID | None = None
    lawsuit_id: uuid.UUID | None = None


class ResolvedTemplateResponse(BaseModel):
    content: str
    header_content: str
    footer_content: str
    missing: list[str]


class VariableCatalogItem(BaseModel):
    namespace: str
    key: str
    label: str


class GeneratePdfRequest(BaseModel):
    customer_id: uuid.UUID | None = None
    lawsuit_id: uuid.UUID | None = None


class SaveToCloudRequest(BaseModel):
    customer_id: uuid.UUID | None = None
    lawsuit_id: uuid.UUID  # regra 2: sempre obrigatório — é a nuvem do processo


class SendEmailRequest(BaseModel):
    customer_id: uuid.UUID | None = None
    lawsuit_id: uuid.UUID | None = None
    to: EmailStr
    subject: str | None = None


class SavedDocumentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
