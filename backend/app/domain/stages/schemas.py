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
    # Spec 053, regra 1: workflow sugerido ao mover processo para esta etapa. A coluna
    # existe desde a spec 038 — só faltava expor no contrato de escrita.
    suggested_workflow_id: uuid.UUID | None = None


class StageUpdateRequest(_StagnantDaysMixin):
    name: str
    step_id: int
    is_active: bool = True
    suggested_workflow_id: uuid.UUID | None = None


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
    """`from_id`/`to_id` são ids de `stages` (regra 4). A reatribuição é real desde a
    spec 101 (regra 2): move `lawsuits.stage_id` e devolve a contagem em
    `transferred_count`."""

    from_id: uuid.UUID
    to_id: uuid.UUID
