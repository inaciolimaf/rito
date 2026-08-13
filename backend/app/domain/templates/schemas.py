import uuid
from datetime import datetime

from pydantic import BaseModel

from app.domain.templates.models import TemplateType


class TemplateCreateRequest(BaseModel):
    name: str
    type: TemplateType
    content: str = ""


class TemplateUpdateRequest(BaseModel):
    name: str
    type: TemplateType
    content: str = ""


class TemplateResponse(BaseModel):
    id: uuid.UUID
    name: str
    type: TemplateType
    content: str
    created_by: uuid.UUID
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TemplateListResponse(BaseModel):
    items: list[TemplateResponse]
    next_cursor: str | None
    total: int
