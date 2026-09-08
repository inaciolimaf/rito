import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.task_types.models import TaskComplexity, TaskDuration


class TaskTypeCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    step_id: int | None = None
    complexity: TaskComplexity | None = None
    duration: TaskDuration | None = None
    # Regra 8: reward ≥ 0; zero válido. None = aceitar a sugestão da matriz (regra 2).
    reward: int | None = Field(default=None, ge=0)
    show_in_schedule: bool = False


class TaskTypeUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    step_id: int | None = None
    complexity: TaskComplexity | None = None
    duration: TaskDuration | None = None
    reward: int = Field(ge=0)
    show_in_schedule: bool = False
    is_active: bool = True


class SuggestRewardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    complexity: TaskComplexity
    duration: TaskDuration


class SuggestRewardResponse(BaseModel):
    reward: int


class TaskTypeTransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_id: uuid.UUID
    to_id: uuid.UUID


class TaskTypeResponse(BaseModel):
    id: uuid.UUID
    name: str
    step_id: int | None
    step_name: str | None
    complexity: TaskComplexity | None
    duration: TaskDuration | None
    reward: int
    show_in_schedule: bool
    is_system: bool
    is_active: bool
    # Regra 9 da 031: derivada, nunca armazenada — `MAX(posts.created_at)` entre as
    # tarefas deste tipo que têm responsável (spec 125). `None` quer dizer "nunca
    # atribuído", e só isso: antes da 125 queria dizer "não calculado", que é o que tornava
    # o campo pior que a ausência dele (dívida 25).
    last_assigned_at: datetime | None
    created_at: datetime


class TaskTypeListResponse(BaseModel):
    items: list[TaskTypeResponse]
    total: int
