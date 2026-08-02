from pydantic import BaseModel

from app.domain.courts.models import CourtSegment


class CourtResponse(BaseModel):
    id: int
    code: str
    name: str
    segment: CourtSegment
    state_code: str | None
    datajud_alias: str | None
    is_active: bool


class CourtSystemResponse(BaseModel):
    id: int
    name: str
