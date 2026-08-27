import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import decode_cursor, encode_cursor
from app.domain.action_groups.repository import ActionGroupRepository, LawsuitTypeRepository
from app.domain.automations.engine import AutomationEngine
from app.domain.automations.models import TriggerKind
from app.domain.courts.repository import CourtRepository
from app.domain.financial.repository import TransactionRepository
from app.domain.lawsuits.board_service import BoardService
from app.domain.lawsuits.cnj import (
    CNJNumber,
    CNJValidationError,
    format_cnj,
    infer_court_code,
    parse_cnj,
)
from app.domain.lawsuits.exceptions import (
    CourtSystemIncompatibleError,
    LawsuitTypeNotFoundError,
    ResponsibleNotActiveError,
    StageNotFoundError,
)
from app.domain.lawsuits.listing import (
    EXPORT_ROW_LIMIT,
    LawsuitListingRepository,
    LawsuitListRow,
    filters_from_query,
)
from app.domain.lawsuits.models import Lawsuit
from app.domain.lawsuits.movements_service import MovementsService, TimelinePage
from app.domain.lawsuits.parties_service import PartiesService
from app.domain.lawsuits.repository import LawsuitRepository
from app.domain.lawsuits.schemas import (
    LawsuitBaseRequest,
    LawsuitCreateRequest,
    LawsuitFiltersQuery,
    LawsuitUpdateRequest,
)
from app.domain.lawsuits.stats import LawsuitStats, StatsCache
from app.domain.lawsuits.stats import get_stats as get_lawsuit_stats
from app.domain.stages.repository import StageRepository, StepRepository
from app.domain.users.repository import UserRepository


def _validated_digits(value: str | None) -> str | None:
    """Regra 8 (spec 025): `process_number` é opcional, mas se informado precisa ser um
    número CNJ válido — guardado só com dígitos (regra 9), a máscara é de apresentação."""
    if value is None:
        return None
    digits = "".join(character for character in value if character.isdigit())
    if not digits:
        return None
    parse_cnj(digits)
    return digits


@dataclass
class LawsuitDetail:
    lawsuit: Lawsuit
    action_group_id: uuid.UUID
    action_group_name: str
    step_id: int
    step_name: str


@dataclass
class FinancialSummary:
    """Resumo financeiro (spec 024 §5). Agregados de lançamentos zerados até a spec 056."""

    case_value: Decimal | None
    fees_value: Decimal | None
    received: Decimal
    to_receive: Decimal
    expenses: Decimal
    net_result: Decimal


@dataclass
class InferredCourt:
    id: int
    code: str
    name: str


@dataclass
class NumberValidation:
    valid: bool
    formatted: str | None
    parsed: CNJNumber | None
    inferred_court: InferredCourt | None
    error: str | None


class LawsuitService:
    """CRUD, listagem, dashboard e validação de número. Partes e movimentações vivem
    em `PartiesService`/`MovementsService` (spec 030 — um service por caso de uso)."""

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.lawsuits = LawsuitRepository(session)
        self.types = LawsuitTypeRepository(session)
        self.groups = ActionGroupRepository(session)
        self.stages = StageRepository(session)
        self.steps = StepRepository(session)
        self.users = UserRepository(session)
        self.courts = CourtRepository(session)
        self.listing = LawsuitListingRepository(session)
        self.parties_service = PartiesService(session, tenant_id)
        self.automations = AutomationEngine(session, tenant_id)
        self.movements_service = MovementsService(session, tenant_id)
        self.board_service = BoardService(session, tenant_id)

    async def list_timeline(
        self,
        lawsuit_id: uuid.UUID,
        *,
        kinds: Sequence[str],
        cursor: str | None,
        limit: int,
    ) -> TimelinePage:
        """Compatibilidade (spec 030): a implementação vive em `MovementsService` —
        mantido como delegação fina para não editar testes das specs 026–029."""
        return await self.movements_service.list_timeline(
            lawsuit_id, kinds=kinds, cursor=cursor, limit=limit
        )

    async def list_lawsuits(
        self,
        *,
        payload: LawsuitFiltersQuery,
        order: str,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[LawsuitListRow], str | None, int]:
        # O cursor codifica created_at como texto ISO — comparar timestamptz com literal
        # VARCHAR quebra no Postgres; converter de volta para datetime antes de paginar.
        decoded_cursor: tuple[datetime, uuid.UUID] | None = None
        if cursor:
            raw_value, cursor_id = decode_cursor(cursor)
            decoded_cursor = (datetime.fromisoformat(raw_value), cursor_id)
        items, total = await self.listing.list_filtered(
            filters=filters_from_query(payload),
            descending=order == "desc",
            cursor=decoded_cursor,
            limit=limit,
        )
        next_cursor = None
        if len(items) == limit:
            last = items[-1].lawsuit
            next_cursor = encode_cursor(last.created_at.isoformat(), last.id)
        return list(items), next_cursor, total

    async def export_lawsuits(self, *, payload: LawsuitFiltersQuery) -> list[LawsuitListRow]:
        """Regra 10: export respeita os filtros ativos (não a página visível), com teto."""
        items, _total = await self.listing.list_filtered(
            filters=filters_from_query(payload), limit=EXPORT_ROW_LIMIT
        )
        return list(items)

    async def get_stats(self, *, month: date, cache: StatsCache) -> LawsuitStats:
        """Dashboard (spec 028): agregados do mês com cache de 5 minutos (regra 7)."""
        return await get_lawsuit_stats(self.session, self.tenant_id, month, cache)

    async def get(self, lawsuit_id: uuid.UUID) -> LawsuitDetail | None:
        lawsuit = await self.lawsuits.get_by_id(lawsuit_id)
        if lawsuit is None:
            return None
        return await self._with_derived(lawsuit)

    async def create(self, payload: LawsuitCreateRequest) -> LawsuitDetail:
        await self._validate_references(payload)
        await self.parties_service.validate_party_inputs(payload.parties)
        lawsuit = Lawsuit(
            tenant_id=self.tenant_id,
            user_id=payload.user_id,
            lawsuit_type_id=payload.lawsuit_type_id,
            stage_id=payload.stage_id,
            court_id=payload.court_id,
            court_system_id=payload.court_system_id,
            process_number=_validated_digits(payload.process_number),
            protocol_number=payload.protocol_number,
            originating_process=payload.originating_process,
            folder=payload.folder,
            filing_year=payload.filing_year,
            judiciary=payload.judiciary,
            county=payload.county,
            court_division=payload.court_division,
            process_date=payload.process_date,
            notes=payload.notes,
            case_value=payload.case_value,
            fees_value=payload.fees_value,
            fees_percentage=payload.fees_percentage,
            contingency=payload.contingency,
            closure_date=payload.closure_date,
            transit_date=payload.transit_date,
            archived_date=payload.archived_date,
            outcome=payload.outcome,
        )
        created = await self.lawsuits.create(lawsuit)
        for party_input in payload.parties:
            await self.parties_service.create_party(created.id, party_input)
        # Spec 092: processo novo é gatilho — é onde mora "abriu processo trabalhista,
        # crie a tarefa de cálculo".
        await self.automations.emit(
            TriggerKind.LAWSUIT_CREATED.value,
            payload={
                "lawsuit_id": str(created.id),
                "lawsuit_type_id": str(created.lawsuit_type_id),
                "stage_id": str(created.stage_id),
                "user_id": str(created.user_id),
            },
            subject_type="lawsuit",
            subject_id=created.id,
        )
        return await self._with_derived(created)

    async def update(
        self, lawsuit: Lawsuit, payload: LawsuitUpdateRequest, *, changed_by: uuid.UUID
    ) -> LawsuitDetail:
        await self._validate_references(payload)
        lawsuit.user_id = payload.user_id
        lawsuit.lawsuit_type_id = payload.lawsuit_type_id
        # Spec 051, regra 5: troca de etapa "fora do Kanban" (este PUT) também grava
        # lawsuit_stage_history — via BoardService.change_stage, o único caminho que grava.
        await self.board_service.change_stage(
            lawsuit, to_stage_id=payload.stage_id, changed_by=changed_by
        )
        lawsuit.court_id = payload.court_id
        lawsuit.court_system_id = payload.court_system_id
        lawsuit.process_number = _validated_digits(payload.process_number)
        lawsuit.protocol_number = payload.protocol_number
        lawsuit.originating_process = payload.originating_process
        lawsuit.folder = payload.folder
        lawsuit.filing_year = payload.filing_year
        lawsuit.judiciary = payload.judiciary
        lawsuit.county = payload.county
        lawsuit.court_division = payload.court_division
        lawsuit.process_date = payload.process_date
        lawsuit.notes = payload.notes
        lawsuit.case_value = payload.case_value
        lawsuit.fees_value = payload.fees_value
        lawsuit.fees_percentage = payload.fees_percentage
        lawsuit.contingency = payload.contingency
        lawsuit.closure_date = payload.closure_date
        lawsuit.transit_date = payload.transit_date
        lawsuit.archived_date = payload.archived_date
        lawsuit.outcome = payload.outcome
        lawsuit.is_archived = payload.is_archived
        # `updated_at` tem `onupdate=func.now()` (server-side) — sem um valor explícito, o
        # autoflush disparado pelas consultas de `_with_derived` abaixo expira o atributo
        # (precisa de round-trip para reler) e a leitura síncrona em `_to_response` explode
        # com `MissingGreenlet`. Setar aqui, como `customers.upload_photo` já faz, evita o
        # round-trip por completo.
        lawsuit.updated_at = datetime.now(UTC)
        return await self._with_derived(lawsuit)

    async def delete(self, lawsuit: Lawsuit) -> None:
        # Regra 7: delete é soft — processo com lançamento financeiro nunca é apagado de
        # fato (não há tabela financeira ainda para checar, então hoje é sempre soft).
        lawsuit.is_archived = True

    async def financial_summary(self, lawsuit: Lawsuit) -> FinancialSummary:
        """Regra 11 (spec 056): agregados vêm de `transactions` via
        `TransactionRepository.lawsuit_financial_totals` — só o que foi pago compõe
        `received`/`expenses`; `to_receive` é RECEITA em aberto."""
        totals = await TransactionRepository(session=self.session).lawsuit_financial_totals(
            lawsuit.id
        )
        return FinancialSummary(
            case_value=lawsuit.case_value,
            fees_value=lawsuit.fees_value,
            received=totals.received,
            to_receive=totals.to_receive,
            expenses=totals.expenses,
            net_result=totals.received - totals.expenses,
        )

    async def validate_number(self, process_number: str) -> NumberValidation:
        """Spec 025 §5: valida o número e infere o tribunal do catálogo (regra 7 —
        sem correspondência, `inferred_court` é None sem invalidar o número)."""
        try:
            parsed = parse_cnj(process_number)
        except CNJValidationError as exc:
            return NumberValidation(
                valid=False, formatted=None, parsed=None, inferred_court=None, error=str(exc)
            )
        inferred: InferredCourt | None = None
        court_code = infer_court_code(parsed)
        if court_code is not None:
            court = await self.courts.get_by_code(court_code)
            if court is not None:
                inferred = InferredCourt(id=court.id, code=court.code, name=court.name)
        return NumberValidation(
            valid=True,
            formatted=format_cnj(parsed),
            parsed=parsed,
            inferred_court=inferred,
            error=None,
        )

    async def _validate_references(self, payload: LawsuitBaseRequest) -> None:
        if await self.types.get_by_id(payload.lawsuit_type_id) is None:
            raise LawsuitTypeNotFoundError
        if await self.stages.get_by_id(payload.stage_id) is None:
            raise StageNotFoundError
        responsible = await self.users.get_by_id(payload.user_id)
        if responsible is None or not responsible.is_active:
            raise ResponsibleNotActiveError
        if payload.court_id is not None and payload.court_system_id is not None:
            compatible = await self.courts.is_system_compatible(
                court_id=payload.court_id, system_id=payload.court_system_id
            )
            if not compatible:
                raise CourtSystemIncompatibleError

    async def _with_derived(self, lawsuit: Lawsuit) -> LawsuitDetail:
        lawsuit_type = await self.types.get_by_id(lawsuit.lawsuit_type_id)
        assert lawsuit_type is not None
        group = await self.groups.get_by_id(lawsuit_type.action_group_id)
        assert group is not None
        stage = await self.stages.get_by_id(lawsuit.stage_id)
        assert stage is not None
        step = await self.steps.get_by_step_id(stage.step_id)
        assert step is not None
        return LawsuitDetail(
            lawsuit=lawsuit,
            action_group_id=group.id,
            action_group_name=group.name,
            step_id=step.id,
            step_name=step.name,
        )
