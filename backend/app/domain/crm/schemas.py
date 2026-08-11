import uuid
from datetime import date, datetime

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
    # Spec 052, regra 7: badge + tooltip ("estagnado há N dias, limite da etapa é M").
    is_stagnant: bool
    stagnant_since: date | None
    stagnant_days: int | None


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


class CrmStatsByStepResponse(BaseModel):
    step_id: int
    step_name: str
    total: int
    stagnant_count: int


class CrmStatsResponse(BaseModel):
    total_lawsuits: int
    received_this_month: int
    total_value: JsonDecimal
    stagnant_count: int
    stagnant_value: JsonDecimal
    by_step: list[CrmStatsByStepResponse]


class RecalculateStagnationResponse(BaseModel):
    recalculated_count: int
