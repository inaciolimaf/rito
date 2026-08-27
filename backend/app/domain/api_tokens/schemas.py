import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApiTokenCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    scopes: list[str] = Field(min_length=1)
    allowed_ips: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None


class ApiTokenResponse(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str
    scopes: list[str]
    allowed_ips: list[str]
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None
    is_active: bool
    created_at: datetime
    # Regra 1: preenchido só na criação. Numa listagem é sempre nulo.
    token: str | None = None


class ApiTokenListResponse(BaseModel):
    items: list[ApiTokenResponse]
    total: int


class ScopeResponse(BaseModel):
    scope: str
    description: str


class ApiUsageRow(BaseModel):
    path: str
    method: str
    calls: int
    errors: int
    avg_duration_ms: int | None


class ApiUsageResponse(BaseModel):
    items: list[ApiUsageRow]
    total_calls: int
