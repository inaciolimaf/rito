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


class PostFlagsInput(BaseModel):
    """As 5 flags do post (spec 033 §5) — combináveis livremente (regra 10)."""

    model_config = ConfigDict(extra="forbid")

    is_important: bool = False
    is_urgent: bool = False
    is_future: bool = False
    is_private: bool = False
    show_in_schedule: bool = False


class PostCreateRequest(PostBaseRequest, PostFlagsInput):
    """`user_ids` OU `squad_id` (regra 2: o time expande para os membros ativos) —
    ao menos um responsável é obrigatório DEPOIS da expansão."""

    user_ids: list[uuid.UUID] = []
    squad_id: uuid.UUID | None = None


class PostUpdateRequest(PostBaseRequest):
    user_ids: list[uuid.UUID]


class PostFlagsRequest(PostFlagsInput):
    """PUT /posts/{id}/flags — todas as flags de uma vez (mesmo padrão dos outros PUTs)."""


class PostCompleteRequest(BaseModel):
    """Conclusão (regras 1, 4, 9): `completed_at` só para lançamento retroativo (nunca
    no futuro — regra 4); `user_id` só honrado por ADMINISTRADOR+ (regra 9)."""

    model_config = ConfigDict(extra="forbid")

    completed_at: datetime | None = None
    user_id: uuid.UUID | None = None


class PostReopenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID | None = None


class PostFlagValueRequest(BaseModel):
    """read/star: set idempotente (default true) — chamar de novo não desmarca por
    acidente; para desmarcar, value=false explícito."""

    model_config = ConfigDict(extra="forbid")

    value: bool = True


class AssigneeResponse(BaseModel):
    id: uuid.UUID
    name: str
    completed_at: datetime | None
    points_earned: int | None
    completed_by: uuid.UUID | None
    is_read: bool
    is_starred: bool


class PostResponse(BaseModel):
    id: uuid.UUID
    lawsuit_id: uuid.UUID
    task_type_id: uuid.UUID | None
    task_type_name: str
    created_by: uuid.UUID | None
    scheduled_date: date | None
    scheduled_time: time | None
    end_date: date | None
    end_time: time | None
    deadline_date: date | None
    all_day: bool
    location: str | None
    comments: str | None
    reward_snapshot: int
    is_important: bool
    is_urgent: bool
    is_future: bool
    is_private: bool
    show_in_schedule: bool
    # Regra 3: concluída como um todo quando TODOS os responsáveis concluíram.
    all_completed: bool
    # Regra 8: tarefa privada aparece para não envolvidos só como presença — conteúdo
    # redigido (ver service); sempre False em respostas diretas a envolvidos.
    redacted: bool = False
    assignees: list[AssigneeResponse]
    created_at: datetime
    updated_at: datetime
