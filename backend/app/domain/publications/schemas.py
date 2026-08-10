import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class PublicationImportRequest(BaseModel):
    """Item bruto de `items[]` do DJEN — o parse (integrations/djen) valida."""

    # Any: é o payload arbitrário da API externa; validar campo a campo aqui
    # duplicaria o parser (fonte única da verdade — spec 042, regra 10).
    item: dict[str, Any] = Field()


class PublicationResponse(BaseModel):
    id: uuid.UUID
    external_id: int
    hash: str
    availability_date: date
    court_code: str
    communication_type: str | None
    process_number: str | None
    status: str | None
    is_active: bool
    lawsuit_id: uuid.UUID | None
    created_at: datetime
