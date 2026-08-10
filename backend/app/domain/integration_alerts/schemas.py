import uuid
from datetime import datetime

from pydantic import BaseModel


class IntegrationAlertResponse(BaseModel):
    id: uuid.UUID
    integration: str
    severity: str
    code: str
    message: str
    created_at: datetime


class IntegrationAlertListResponse(BaseModel):
    items: list[IntegrationAlertResponse]
    total: int
