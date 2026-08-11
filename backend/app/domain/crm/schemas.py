import uuid
from datetime import datetime

from pydantic import BaseModel

from app.domain.lawsuits.schemas import JsonDecimal


class BoardCardResponse(BaseModel):
    id: uuid.UUID
    process_number: str | None
    folder: str | None
    lawsuit_type_name: str
    stage_id: uuid.UUID
    stage_name: str
    case_value: JsonDecimal | None
    responsible_id: uuid.UUID
    responsible_name: str
    stage_entered_at: datetime
    parties: list[dict[str, object]]
    parties_total: int


class BoardColumnResponse(BaseModel):
    step_id: int
    step_name: str
    total: int
    items: list[BoardCardResponse]


class BoardResponse(BaseModel):
    columns: list[BoardColumnResponse]
    total: int
    suggest_refine_filters: bool  # regra 11: sugestão, nunca bloqueia


class BoardColumnPageResponse(BaseModel):
    items: list[BoardCardResponse]
    next_cursor: str | None
    total: int
