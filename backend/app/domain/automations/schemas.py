import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_kind: str
    action_config: dict[str, Any] = Field(default_factory=dict)
    delay_kind: str = "immediate"
    delay_value: int | None = Field(default=None, ge=0, le=365)
    condition: dict[str, Any] | None = None
    branches: dict[str, list[int]] | None = None


class AutomationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    description: str | None = None
    trigger_kind: str
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    actions: list[ActionRequest] = Field(default_factory=list)


class ActionResponse(BaseModel):
    id: uuid.UUID
    position: int
    action_kind: str
    action_config: dict[str, Any]
    delay_kind: str
    delay_value: int | None
    condition: dict[str, Any] | None


class AutomationResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    trigger_kind: str
    trigger_config: dict[str, Any]
    is_active: bool
    monthly_ai_budget_usd: float | None = None
    current_month_spend_usd: float = 0.0
    created_by: uuid.UUID
    created_at: datetime
    actions: list[ActionResponse]


class AutomationListResponse(BaseModel):
    items: list[AutomationResponse]
    total: int


class ToggleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool


class TestRequest(BaseModel):
    """O retrato do sujeito que a simulação deve considerar (regra 10)."""

    model_config = ConfigDict(extra="forbid")

    payload: dict[str, Any] = Field(default_factory=dict)


class SimulatedStepResponse(BaseModel):
    position: int
    action_kind: str
    status: str
    detail: dict[str, Any]
    scheduled_for: str | None


class TestResponse(BaseModel):
    """`persisted: false` é campo da resposta, não promessa da documentação: um 'teste'
    que grava é a pior armadilha possível numa tela chamada Testar."""

    steps: list[SimulatedStepResponse]
    persisted: bool = False


class RunStepResponse(BaseModel):
    position: int
    action_kind: str
    status: str
    detail: dict[str, Any] | None
    error: str | None
    created_at: datetime


class RunResponse(BaseModel):
    id: uuid.UUID
    automation_id: uuid.UUID
    subject_type: str | None
    subject_id: uuid.UUID | None
    status: str
    actions_completed: int
    chain_depth: int
    next_position: int | None
    next_action_at: datetime | None
    error: str | None
    started_at: datetime
    finished_at: datetime | None
    steps: list[RunStepResponse]


class RunListResponse(BaseModel):
    items: list[RunResponse]
    total: int


class AiBudgetRequest(BaseModel):
    """Teto de IA DESTA automação (spec 094, regra 6). Nulo é sem teto."""

    model_config = ConfigDict(extra="forbid")

    monthly_ai_budget_usd: Decimal | None = Field(default=None, ge=0, le=100_000)


class DecisionResponse(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    action_id: uuid.UUID
    question: str
    context_summary: str | None
    chosen_branch: str | None
    confidence: float | None
    reasoning: str
    model: str
    tokens_used: int | None
    cost_usd: float | None
    fell_back: bool
    fallback_reason: str | None
    created_at: datetime


class DecisionListResponse(BaseModel):
    items: list[DecisionResponse]
    total: int


class SimulateDecisionRequest(BaseModel):
    """Regra 10: roda a decisão e NÃO executa as ações do ramo."""

    model_config = ConfigDict(extra="forbid")

    payload: dict[str, Any] = Field(default_factory=dict)
    position: int | None = None


class SimulateDecisionResponse(BaseModel):
    position: int
    question: str
    chosen_branch: str
    confidence: float | None
    reasoning: str
    fell_back: bool
    fallback_reason: str | None
    executed: bool = False
