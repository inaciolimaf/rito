from datetime import datetime

from pydantic import BaseModel

from app.domain.monitored_terms.models import TermStatus


class IntegrationStatusItemResponse(BaseModel):
    integration: str
    is_healthy: bool | None
    last_success_at: datetime | None
    avg_latency_ms: float | None
    failures_24h: int


class TermsByStatusItemResponse(BaseModel):
    status: TermStatus
    count: int


class IntegrationStatusResponse(BaseModel):
    integrations: list[IntegrationStatusItemResponse]
    terms_by_status: list[TermsByStatusItemResponse]
