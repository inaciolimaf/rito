import uuid
from datetime import datetime

from pydantic import BaseModel, model_validator


class StepResponse(BaseModel):
    id: int
    name: str
    position: int


class _StagnantDaysMixin(BaseModel):
    enable_stagnant_days: bool = False
    stagnant_days: int | None = None

    @model_validator(mode="after")
    def _validate_stagnant_days(self) -> "_StagnantDaysMixin":
        """Regra 3: `enable_stagnant_days=true` exige `stagnant_days > 0` (mesma checagem
        do CHECK constraint no banco — aqui só para devolver 422 antes de ir ao banco)."""
        if self.enable_stagnant_days and not (self.stagnant_days and self.stagnant_days > 0):
            raise ValueError(
                "stagnant_days deve ser maior que zero quando a estagnação está ativa."
            )
        return self


class StageCreateRequest(_StagnantDaysMixin):
    name: str
    step_id: int


class StageUpdateRequest(_StagnantDaysMixin):
    name: str
    step_id: int
    is_active: bool = True


class StageResponse(BaseModel):
    id: uuid.UUID
    name: str
    step_id: int
    step_name: str
    position: int
    enable_stagnant_days: bool
    stagnant_days: int | None
    suggested_workflow_id: uuid.UUID | None
    is_active: bool
    created_at: datetime


class StageListResponse(BaseModel):
    items: list[StageResponse]
    next_cursor: None = None
    total: int


class ReorderStagesRequest(BaseModel):
    stage_ids: list[uuid.UUID]


class TransferStagesRequest(BaseModel):
    """`from_id`/`to_id` são ids de `stages` (regra 4) — nada referencia `stage_id` ainda
    (spec 015, Descobertas: `lawsuits` só chega na spec 022), então a migração hoje não move
    nenhum dado real; o contrato fica pronto para quando houver o que mover."""

    from_id: uuid.UUID
    to_id: uuid.UUID
