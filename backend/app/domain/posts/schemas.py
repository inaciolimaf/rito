import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, model_validator


class PostBaseRequest(BaseModel):
    """Campos do post (spec 032 §5). As constraints de ciclo de datas repetem as CHECKs
    do banco (regras 5–6) — aqui o erro vira 422 em vez de 500."""

    model_config = ConfigDict(extra="forbid")

    lawsuit_id: uuid.UUID
    task_type_id: uuid.UUID
    scheduled_date: date | None = None
    scheduled_time: time | None = None
    end_date: date | None = None
    end_time: time | None = None
    deadline_date: date | None = None
    all_day: bool = False
    location: str | None = None
    comments: str | None = None

    @model_validator(mode="after")
    def _check_cycle(self) -> "PostBaseRequest":
        if self.end_time is not None and self.end_date is None:
            raise ValueError("Hora de término exige data de término.")
        if (
            self.end_date is not None
            and self.scheduled_date is not None
            and self.end_date < self.scheduled_date
        ):
            raise ValueError("Data de término não pode ser anterior à data do compromisso.")
        return self


class PostCreateRequest(PostBaseRequest):
    """`user_ids` OU `squad_id` (regra 2: o time expande para os membros ativos) —
    ao menos um responsável é obrigatório DEPOIS da expansão."""

    user_ids: list[uuid.UUID] = []
    squad_id: uuid.UUID | None = None


class PostUpdateRequest(PostBaseRequest):
    user_ids: list[uuid.UUID]


class AssigneeResponse(BaseModel):
    id: uuid.UUID
    name: str


class PostResponse(BaseModel):
    id: uuid.UUID
    lawsuit_id: uuid.UUID
    task_type_id: uuid.UUID
    task_type_name: str
    created_by: uuid.UUID
    scheduled_date: date | None
    scheduled_time: time | None
    end_date: date | None
    end_time: time | None
    deadline_date: date | None
    all_day: bool
    location: str | None
    comments: str | None
    reward_snapshot: int
    assignees: list[AssigneeResponse]
    created_at: datetime
    updated_at: datetime
