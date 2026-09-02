import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.schemas import JsonDecimal
from app.domain.lawsuits.models import ContingencyLevel, LawsuitOutcome, MovementOrigin, PartyPole

# Os 5 tipos da timeline (spec 026 §4). Os slots `task`/`publication`/`transaction` ficam
# sem fonte até as specs 032/042/056 — não entram no union enquanto a tabela não existe.
#
# Vocabulário do contrato (`?kinds=`), por isso mora aqui: o router precisa dele para
# aplicar a regra 2 da 026 — omitir o parâmetro traz todos os tipos, `kinds=` vazio traz
# nenhum — e ia buscá-lo em `repository.py` (spec 118, checagem 2). A regra continua no
# router, que é onde ela estava: só o lugar da constante mudou.
TIMELINE_KINDS = ("task", "movement_auto", "movement_manual", "publication", "transaction")


class LawsuitBaseRequest(BaseModel):
    # extra="forbid": regra 2 — `action_group_id`/`step_id` são derivados e nunca aceitos
    # do cliente; enviá-los (ou qualquer outro campo desconhecido) precisa virar 422.
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID
    lawsuit_type_id: uuid.UUID
    stage_id: uuid.UUID
    court_id: int | None = None
    court_system_id: int | None = None
    process_number: str | None = None
    protocol_number: str | None = None
    originating_process: str | None = None
    folder: str | None = Field(default=None, max_length=30)
    filing_year: int | None = None
    judiciary: str | None = None
    county: str | None = None
    court_division: str | None = None
    process_date: date | None = None
    notes: str | None = None
    # Honorários e ciclo (spec 024). Regra 7: negativos → 422 (ge=0).
    # Regra 2: percentual entre 0 e 100.
    case_value: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    fees_value: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    fees_percentage: Decimal | None = Field(
        default=None, ge=0, le=100, max_digits=5, decimal_places=2
    )
    contingency: ContingencyLevel | None = None
    closure_date: date | None = None
    transit_date: date | None = None
    archived_date: date | None = None
    outcome: LawsuitOutcome | None = None

    @model_validator(mode="after")
    def _validate_cycle(self) -> "LawsuitBaseRequest":
        # Regra 3: fechamento ≤ trânsito ≤ arquivamento (o banco tem a mesma trava em
        # ck_cycle; aqui o erro vira 422 em vez de 500).
        if (
            self.closure_date is not None
            and self.transit_date is not None
            and self.transit_date < self.closure_date
        ):
            raise ValueError("Trânsito em julgado não pode ser anterior ao fechamento.")
        if (
            self.transit_date is not None
            and self.archived_date is not None
            and self.archived_date < self.transit_date
        ):
            raise ValueError("Arquivamento não pode ser anterior ao trânsito em julgado.")
        # Regra 4: resultado exige processo fechado.
        if self.outcome is not None and self.closure_date is None:
            raise ValueError("Resultado só é aceito com a data de fechamento preenchida.")
        return self


class PartyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: uuid.UUID
    pole: PartyPole
    is_client: bool = True


class LawsuitCreateRequest(LawsuitBaseRequest):
    # Regra 1: processo nasce com no mínimo 1 parte — sem `parties` (ou lista vazia) é 422.
    parties: list[PartyInput] = Field(min_length=1)


class LawsuitUpdateRequest(LawsuitBaseRequest):
    # PUT não aceita `parties` — partes mudam só pelos endpoints dedicados
    # `/lawsuits/{id}/parties` (spec 023 §5).
    is_archived: bool = False


class PartyCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: uuid.UUID
    pole: PartyPole
    is_client: bool = True


class PartyUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pole: PartyPole
    is_client: bool | None = None


class LawsuitResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    lawsuit_type_id: uuid.UUID
    action_group_id: uuid.UUID
    action_group_name: str
    stage_id: uuid.UUID
    step_id: int
    step_name: str
    court_id: int | None
    court_system_id: int | None
    process_number: str | None
    protocol_number: str | None
    originating_process: str | None
    folder: str | None
    filing_year: int | None
    judiciary: str | None
    county: str | None
    court_division: str | None
    process_date: date | None
    notes: str | None
    case_value: JsonDecimal | None
    fees_value: JsonDecimal | None
    fees_percentage: JsonDecimal | None
    contingency: ContingencyLevel | None
    closure_date: date | None
    transit_date: date | None
    archived_date: date | None
    outcome: LawsuitOutcome | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class FinancialSummaryResponse(BaseModel):
    """Resumo financeiro do processo (spec 024 §5). Os agregados de lançamentos
    (`received`, `to_receive`, `expenses`, `net_result`) são calculados sobre
    `transactions` desde a spec 056."""

    case_value: JsonDecimal | None
    fees_value: JsonDecimal | None
    received: JsonDecimal
    to_receive: JsonDecimal
    expenses: JsonDecimal
    net_result: JsonDecimal


class PartyResponse(BaseModel):
    id: uuid.UUID
    lawsuit_id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str
    pole: PartyPole
    is_client: bool
    created_at: datetime


class ValidateNumberRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    process_number: str = Field(min_length=1)


class ParsedCNJResponse(BaseModel):
    sequential: str
    check_digit: str
    year: int
    segment: int
    segment_name: str
    court: str
    origin: str


class InferredCourtResponse(BaseModel):
    id: int
    code: str
    name: str


class ValidateNumberResponse(BaseModel):
    valid: bool
    formatted: str | None
    parsed: ParsedCNJResponse | None
    inferred_court: InferredCourtResponse | None
    error: str | None


class MovementCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occurred_at: datetime
    title: str = Field(min_length=1, max_length=500)
    body: str | None = None


class MovementUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occurred_at: datetime
    title: str = Field(min_length=1, max_length=500)
    body: str | None = None


class MovementResponse(BaseModel):
    id: uuid.UUID
    lawsuit_id: uuid.UUID
    origin: MovementOrigin
    occurred_at: datetime
    title: str
    body: str | None
    header: str | None
    external_code: int | None
    external_id: str | None
    created_by: uuid.UUID | None
    created_at: datetime


class TimelineItemResponse(BaseModel):
    kind: str
    id: uuid.UUID
    occurred_at: datetime
    title: str
    summary: str | None
    actor: str | None
    metadata: dict[str, object]


class TimelineResponse(BaseModel):
    items: list[TimelineItemResponse]
    next_cursor: str | None
    total: int


class PartyBriefResponse(BaseModel):
    name: str
    pole: PartyPole


class LawsuitListItemResponse(BaseModel):
    id: uuid.UUID
    process_number: str | None
    folder: str | None
    is_archived: bool
    created_at: datetime
    last_movement_at: datetime | None
    last_movement_title: str | None
    lawsuit_type_name: str
    action_group_name: str
    stage_name: str
    parties: list[PartyBriefResponse]
    parties_total: int


class LawsuitListResponse(BaseModel):
    items: list[LawsuitListItemResponse]
    next_cursor: str | None
    total: int


class StatsCardResponse(BaseModel):
    """Card do dashboard (spec 028 §5). `delta_pct` None = "novo" (regra 2)."""

    value: int
    delta_pct: float | None
    previous: int


class StepVolumeResponse(BaseModel):
    step: str
    count: int
    pct: float


class ClosureGoalResponse(BaseModel):
    """Widget de meta (spec 028) — a meta em si é configurada na spec 039."""

    target: int
    achieved: int
    pct: float


class LawsuitStatsResponse(BaseModel):
    active: StatsCardResponse
    closed_this_month: StatsCardResponse
    archived_this_month: StatsCardResponse
    volume_by_step: list[StepVolumeResponse]
    # None = sem meta configurada — o widget convida a configurar (regra 6).
    closure_goal: ClosureGoalResponse | None = None


class FolderSuggestionResponse(BaseModel):
    """Sugestão do autocomplete de pasta (spec 029 §5) — nome na grafia armazenada."""

    name: str
    count: int


class FolderRenameRequest(BaseModel):
    """Renomear em lote (regra 3). `merge` é a confirmação explícita da fusão (regra 4);
    nomes limitados a 30 caracteres como o campo (regra 5)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_name: str = Field(min_length=1, max_length=30, alias="from")
    to_name: str = Field(min_length=1, max_length=30, alias="to")
    merge: bool = False


class FolderRenameResponse(BaseModel):
    folder: str
    updated: int
    merged: bool


class FolderGroupItemResponse(BaseModel):
    id: uuid.UUID
    process_number: str | None
    is_archived: bool
    created_at: datetime


class FolderGroupResponse(BaseModel):
    name: str
    count: int
    items: list[FolderGroupItemResponse]


class LawsuitGroupsResponse(BaseModel):
    groups: list[FolderGroupResponse]


class LawsuitFiltersQuery(BaseModel):
    """Filtros da listagem (spec 027 §5) — usado tanto como modelo de query string do
    GET `/lawsuits` (FastAPI 0.115+: `Annotated[..., Query()]`) quanto como corpo do
    POST `/lawsuits/export`. Multivalorados chegam separados por vírgula."""

    model_config = ConfigDict(extra="forbid")

    view: str = "all"
    q: str | None = None
    customer_id: uuid.UUID | None = None
    identification: str | None = None
    process_number: str | None = None
    protocol_number: str | None = None
    folder: str | None = None
    notes: str | None = None
    action_group_id: str | None = None
    lawsuit_type_id: str | None = None
    step_id: str | None = None
    stage_id: str | None = None
    court_id: str | None = None
    court_system_id: str | None = None
    user_id: str | None = None
    contingency: str | None = None
    origin_id: str | None = None
    customer_type: str | None = None
    created_from: date | None = None
    created_to: date | None = None
    process_date_from: date | None = None
    process_date_to: date | None = None
    closure_from: date | None = None
    closure_to: date | None = None
    transit_from: date | None = None
    transit_to: date | None = None
    archived_from: date | None = None
    archived_to: date | None = None
    archived: bool | None = None
    # Spec 052 §5: "todos"/"só estagnados"/"só em andamento" — filtro do board do CRM,
    # mas vive no schema compartilhado (regra 8 da spec 051: mesmos filtros de /lawsuits).
    display_stagnant: Literal["all", "stagnant", "active"] = "all"


class LawsuitExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["xlsx", "pdf"]
    filters: LawsuitFiltersQuery


class SyncStatusResponse(BaseModel):
    last_sync_at: datetime | None
    last_update: datetime | None
    not_found_count: int
    is_syncing: bool


class SyncMovementsResponse(BaseModel):
    status: str
    new_movements: int
    last_sync_at: datetime | None
    last_update: datetime | None
    not_found_count: int


class SyncRunResponse(BaseModel):
    """Spec 050, alvo 1 — mesma `sync_runs` do DJEN (spec 043), lado `lawsuit_id`."""

    id: uuid.UUID
    started_at: datetime
    finished_at: datetime | None
    found_count: int
    new_count: int
    error: str | None


class SyncRunListResponse(BaseModel):
    items: list[SyncRunResponse]


class MoveStageRequest(BaseModel):
    """Spec 051, regra 3: o front resolve a etapa exata (primeira da fase destino,
    por `position`) antes de chamar — este endpoint só aplica e grava histórico."""

    stage_id: uuid.UUID


class BulkMoveStageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lawsuit_ids: list[uuid.UUID]
    stage_id: uuid.UUID


class BulkMoveStageResponse(BaseModel):
    moved: int


class SuggestedWorkflowResponse(BaseModel):
    id: uuid.UUID
    name: str


class MoveStageResponse(BaseModel):
    """Spec 053, regra 1: mover passa a devolver a sugestão de workflow da etapa
    destino — `null` se a etapa não tem workflow configurado ou está suprimido
    para este processo (regra 6/7). Ação em massa nunca sugere (regra 10) — o
    endpoint de bulk continua devolvendo só `BulkMoveStageResponse`."""

    lawsuit: LawsuitResponse
    suggested_workflow: SuggestedWorkflowResponse | None


class ApplyWorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: uuid.UUID
    stage_id: uuid.UUID | None = None
    confirm_duplicate: bool = False


class SkippedWorkflowStepResponse(BaseModel):
    task_type_name: str
    reason: str


class ApplyWorkflowResponse(BaseModel):
    application_id: uuid.UUID
    created: int
    post_ids: list[uuid.UUID]
    skipped: list[SkippedWorkflowStepResponse]


class SuppressWorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_id: uuid.UUID


class WorkflowApplicationResponse(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_name: str
    stage_id: uuid.UUID | None
    applied_by: uuid.UUID
    posts_created: list[uuid.UUID]
    applied_at: datetime


class WorkflowApplicationListResponse(BaseModel):
    items: list[WorkflowApplicationResponse]
