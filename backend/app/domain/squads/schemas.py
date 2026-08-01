import uuid
from datetime import datetime

from pydantic import BaseModel


class SquadMemberSummary(BaseModel):
    id: uuid.UUID
    name: str
    avatar_url: str | None


class SquadCreateRequest(BaseModel):
    name: str
    member_ids: list[uuid.UUID] = []


class SquadUpdateRequest(BaseModel):
    name: str
    is_active: bool = True
    member_ids: list[uuid.UUID] = []


class SquadResponse(BaseModel):
    id: uuid.UUID
    name: str
    is_active: bool
    members: list[SquadMemberSummary]
    created_at: datetime
    updated_at: datetime


class SquadListResponse(BaseModel):
    items: list[SquadResponse]
    next_cursor: str | None
    total: int
