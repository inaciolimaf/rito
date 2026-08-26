import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class ModelInfoResponse(BaseModel):
    id: str
    name: str
    context_length: int
    # Preço por token, como o OpenRouter publica — a UI multiplica por 1M para exibir.
    prompt_price_usd: float
    completion_price_usd: float


class ModelCatalogResponse(BaseModel):
    items: list[ModelInfoResponse]
    total: int
    # Regra 11: sem chave, o catálogo vem vazio e a UI explica em vez de quebrar.
    is_configured: bool


class FeatureConfigResponse(BaseModel):
    feature_key: str
    label: str
    description: str
    model: str
    fallback_model: str | None
    temperature: float
    max_tokens: int | None
    is_enabled: bool
    store_prompts: bool
    is_default: bool


class FeatureConfigListResponse(BaseModel):
    items: list[FeatureConfigResponse]
    is_configured: bool
    default_model: str


class FeatureConfigRequest(BaseModel):
    feature_key: str
    model: str = Field(min_length=1)
    fallback_model: str | None = None
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    is_enabled: bool = True
    # Regra 13: opt-in explícito para guardar prompt e resposta.
    store_prompts: bool = False


class UsageGroupResponse(BaseModel):
    key: str
    calls: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    errors: int


class UsageTotalsResponse(BaseModel):
    calls: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    errors: int
    avg_latency_ms: int | None


class UsageResponse(BaseModel):
    group_by: str
    from_: date | None = Field(default=None, alias="from")
    to: date | None = None
    items: list[UsageGroupResponse]
    totals: UsageTotalsResponse

    model_config = {"populate_by_name": True}


class UsageRecordResponse(BaseModel):
    id: uuid.UUID
    feature_key: str
    model: str
    status: str


class ThreadCreateRequest(BaseModel):
    graph_name: str
    input: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    title: str | None = Field(default=None, max_length=200)
    # `false` cria o thread parado, para o cliente abrir o SSE e assistir do 1º passo.
    autorun: bool = True


class ThreadResumeRequest(BaseModel):
    approved: bool
    human_input: dict[str, Any] | None = None


class PendingActionResponse(BaseModel):
    kind: str
    title: str
    preview: dict[str, Any]
    description: str | None = None


class ThreadResponse(BaseModel):
    id: uuid.UUID
    graph_name: str
    feature_key: str
    title: str | None
    status: str
    context: dict[str, Any]
    pending_action: PendingActionResponse | None
    output: dict[str, Any] | None
    error: str | None
    step_count: int
    user_id: uuid.UUID
    waiting_since: datetime | None
    created_at: datetime
    updated_at: datetime


class ThreadListResponse(BaseModel):
    items: list[ThreadResponse]
    next_cursor: str | None
    total: int


class StepResponse(BaseModel):
    id: uuid.UUID
    step: int
    node: str
    kind: str
    input: dict[str, Any] | None
    output: dict[str, Any] | None
    duration_ms: int | None
    error: str | None
    created_at: datetime


class StepListResponse(BaseModel):
    items: list[StepResponse]
    total: int


class BudgetRequest(BaseModel):
    """Teto mensal do escritório (spec 090, alvo 2). Nulo é 'sem teto'."""

    monthly_limit_usd: Decimal | None = Field(default=None, ge=0, le=1_000_000)
    alert_pct: int = Field(default=80, ge=1, le=100)
    is_blocking: bool = True


class SpendingAnomalyResponse(BaseModel):
    feature_key: str
    today_usd: float
    daily_average_usd: float
    factor: float


class BudgetResponse(BaseModel):
    monthly_limit_usd: float | None
    spent_usd: float
    used_pct: float | None
    alert_pct: int
    is_blocking: bool
    is_alerting: bool
    is_exceeded: bool
    anomalies: list[SpendingAnomalyResponse]
