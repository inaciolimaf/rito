import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.lawsuits.models import PartyPole


class LawsuitBaseRequest(BaseModel):
    # extra="forbid": regra 2 — `action_group_id`/`step_id` são derivados e nunca aceitos
    # do cliente; enviá-los (ou qualquer outro campo desconhecido) precisa virar 422.
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    lawsuit_type_id: uuid.UUID
    stage_id: uuid.UUID
    court_id: int | None = None
    court_system_id: int | None = None
    process_number: str | None = None
    protocol_number: str | None = None
    originating_process: str | None = None
    folder: str | None = Field(default=None, max_length=30)
    filing_year: int | None = None
    judiciary: str | None = None
    county: str | None = None
    court_division: str | None = None
    process_date: date | None = None
    notes: str | None = None


class PartyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: uuid.UUID
    pole: PartyPole
    is_client: bool = True


class LawsuitCreateRequest(LawsuitBaseRequest):
    # Regra 1: processo nasce com no mínimo 1 parte — sem `parties` (ou lista vazia) é 422.
    parties: list[PartyInput] = Field(min_length=1)


class LawsuitUpdateRequest(LawsuitBaseRequest):
    # PUT não aceita `parties` — partes mudam só pelos endpoints dedicados
    # `/lawsuits/{id}/parties` (spec 023 §5).
    is_archived: bool = False


class PartyCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: uuid.UUID
    pole: PartyPole
    is_client: bool = True


class PartyUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pole: PartyPole
    is_client: bool | None = None


class LawsuitResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    lawsuit_type_id: uuid.UUID
    action_group_id: uuid.UUID
    action_group_name: str
    stage_id: uuid.UUID
    step_id: int
    step_name: str
    court_id: int | None
    court_system_id: int | None
    process_number: str | None
    protocol_number: str | None
    originating_process: str | None
    folder: str | None
    filing_year: int | None
    judiciary: str | None
    county: str | None
    court_division: str | None
    process_date: date | None
    notes: str | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class PartyResponse(BaseModel):
    id: uuid.UUID
    lawsuit_id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str
    pole: PartyPole
    is_client: bool
    created_at: datetime
