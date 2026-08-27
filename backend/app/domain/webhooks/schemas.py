import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EndpointRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    url: str = Field(min_length=8, max_length=2000)
    headers: dict[str, str] = Field(default_factory=dict)


class EndpointResponse(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    headers: dict[str, str]
    is_active: bool
    failure_streak: int
    disabled_at: datetime | None
    created_at: datetime
    # Regra 8: só vem preenchido na criação e na rotação — nunca numa listagem.
    secret: str | None = None


class EndpointListResponse(BaseModel):
    items: list[EndpointResponse]
    total: int


class DeliveryResponse(BaseModel):
    id: uuid.UUID
    endpoint_id: uuid.UUID
    run_id: uuid.UUID | None
    event_kind: str
    payload: dict[str, Any]
    attempt: int
    status_code: int | None
    response_body: str | None
    duration_ms: int | None
    error: str | None
    delivered_at: datetime | None
    next_attempt_at: datetime | None
    created_at: datetime


class DeliveryListResponse(BaseModel):
    items: list[DeliveryResponse]
    total: int


class TestEndpointRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: str = "task.completed"
    payload: dict[str, Any] = Field(default_factory=dict)
