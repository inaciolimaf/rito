import uuid
from datetime import datetime

from pydantic import BaseModel


class IntegrationAlertResponse(BaseModel):
    id: uuid.UUID
    integration: str
    severity: str
    code: str
    message: str
    responsible_user_id: uuid.UUID | None
    resolved_at: datetime | None
    resolved_by: uuid.UUID | None
    created_at: datetime


class IntegrationAlertListResponse(BaseModel):
    items: list[IntegrationAlertResponse]
    total: int
