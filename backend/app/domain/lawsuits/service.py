import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import decode_cursor, encode_cursor
from app.domain.action_groups.repository import ActionGroupRepository, LawsuitTypeRepository
from app.domain.courts.repository import CourtRepository
from app.domain.customers.repository import CustomerRepository
from app.domain.lawsuits.cnj import (
    CNJNumber,
    CNJValidationError,
    format_cnj,
    infer_court_code,
    parse_cnj,
)
from app.domain.lawsuits.exceptions import (
    CourtSystemIncompatibleError,
    DuplicatePartyError,
    LastPartyError,
    LawsuitTypeNotFoundError,
    MovementNotAuthorError,
    PartyCustomerNotFoundError,
    ResponsibleNotActiveError,
    StageNotFoundError,
    TribunalMovementImmutableError,
)
from app.domain.lawsuits.listing import (
    EXPORT_ROW_LIMIT,
    LAWSUIT_VIEWS,
    LawsuitFilters,
    LawsuitListingRepository,
    LawsuitListRow,
)
from app.domain.lawsuits.models import (
    ContingencyLevel,
    Lawsuit,
    LawsuitMovement,
    LawsuitParty,
    MovementOrigin,
    PartyPole,
)
from app.domain.lawsuits.repository import (
    LawsuitMovementRepository,
    LawsuitPartyRepository,
    LawsuitRepository,
    TimelineRow,
    decode_timeline_cursor,
    encode_timeline_cursor,
)
from app.domain.lawsuits.schemas import (
    LawsuitBaseRequest,
    LawsuitCreateRequest,
    LawsuitFiltersQuery,
    LawsuitUpdateRequest,
    MovementCreateRequest,
    MovementUpdateRequest,
    PartyCreateRequest,
    PartyInput,
    PartyUpdateRequest,
)
from app.domain.stages.repository import StageRepository, StepRepository
from app.domain.users.models import User, UserRole
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
class PartyDetail:
    party: LawsuitParty
    customer_name: str


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


@dataclass
class TimelinePage:
    items: Sequence[TimelineRow]
    next_cursor: str | None
    total: int


class LawsuitService:
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
        self.customers = CustomerRepository(session)
        self.parties = LawsuitPartyRepository(session)
        self.movements = LawsuitMovementRepository(session)
        self.listing = LawsuitListingRepository(session)

    def _to_filters(self, payload: LawsuitFiltersQuery) -> LawsuitFilters:
        def uuids(raw: str | None) -> list[uuid.UUID]:
            return [uuid.UUID(value) for value in raw.split(",")] if raw else []

        def ints(raw: str | None) -> list[int]:
            return [int(value) for value in raw.split(",")] if raw else []

        contingencies: list[ContingencyLevel] = []
        if payload.contingency:
            contingencies = [ContingencyLevel(value) for value in payload.contingency.split(",")]
        return LawsuitFilters(
            view=payload.view if payload.view in LAWSUIT_VIEWS else "all",
            q=payload.q,
            customer_id=payload.customer_id,
            identification=payload.identification,
            process_number=payload.process_number,
            protocol_number=payload.protocol_number,
            folder=payload.folder,
            notes=payload.notes,
            action_group_ids=uuids(payload.action_group_id),
            lawsuit_type_ids=uuids(payload.lawsuit_type_id),
            step_ids=ints(payload.step_id),
            stage_ids=uuids(payload.stage_id),
            court_ids=ints(payload.court_id),
            court_system_ids=ints(payload.court_system_id),
            user_ids=uuids(payload.user_id),
            contingencies=contingencies,
            origin_ids=uuids(payload.origin_id),
            customer_type=payload.customer_type,
            created_from=payload.created_from,
            created_to=payload.created_to,
            process_date_from=payload.process_date_from,
            process_date_to=payload.process_date_to,
            closure_from=payload.closure_from,
            closure_to=payload.closure_to,
            transit_from=payload.transit_from,
            transit_to=payload.transit_to,
            archived_from=payload.archived_from,
            archived_to=payload.archived_to,
            archived=payload.archived,
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
            filters=self._to_filters(payload),
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
            filters=self._to_filters(payload), limit=EXPORT_ROW_LIMIT
        )
        return list(items)

    async def get(self, lawsuit_id: uuid.UUID) -> LawsuitDetail | None:
        lawsuit = await self.lawsuits.get_by_id(lawsuit_id)
        if lawsuit is None:
            return None
        return await self._with_derived(lawsuit)

    async def create(self, payload: LawsuitCreateRequest) -> LawsuitDetail:
        await self._validate_references(payload)
        await self._validate_party_inputs(payload.parties)
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
            await self.parties.create(
                LawsuitParty(
                    tenant_id=self.tenant_id,
                    lawsuit_id=created.id,
                    customer_id=party_input.customer_id,
                    pole=party_input.pole,
                    is_client=party_input.is_client,
                )
            )
        return await self._with_derived(created)

    async def update(self, lawsuit: Lawsuit, payload: LawsuitUpdateRequest) -> LawsuitDetail:
        await self._validate_references(payload)
        lawsuit.user_id = payload.user_id
        lawsuit.lawsuit_type_id = payload.lawsuit_type_id
        lawsuit.stage_id = payload.stage_id
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

    async def list_parties(self, lawsuit_id: uuid.UUID) -> Sequence[PartyDetail]:
        rows = await self.parties.list_for_lawsuit(lawsuit_id)
        return [PartyDetail(party=party, customer_name=name) for party, name in rows]

    def financial_summary(self, lawsuit: Lawsuit) -> FinancialSummary:
        zero = Decimal("0.00")
        return FinancialSummary(
            case_value=lawsuit.case_value,
            fees_value=lawsuit.fees_value,
            received=zero,
            to_receive=zero,
            expenses=zero,
            net_result=zero,
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

    async def add_party(self, lawsuit: Lawsuit, payload: PartyCreateRequest) -> PartyDetail:
        customer_name = await self._customer_name(payload.customer_id)
        await self._ensure_not_duplicate(
            lawsuit_id=lawsuit.id, customer_id=payload.customer_id, pole=payload.pole
        )
        party = await self.parties.create(
            LawsuitParty(
                tenant_id=self.tenant_id,
                lawsuit_id=lawsuit.id,
                customer_id=payload.customer_id,
                pole=payload.pole,
                is_client=payload.is_client,
            )
        )
        return PartyDetail(party=party, customer_name=customer_name)

    async def update_party(self, party: LawsuitParty, payload: PartyUpdateRequest) -> PartyDetail:
        if payload.pole != party.pole:
            await self._ensure_not_duplicate(
                lawsuit_id=party.lawsuit_id,
                customer_id=party.customer_id,
                pole=payload.pole,
                exclude_id=party.id,
            )
        party.pole = payload.pole
        if payload.is_client is not None:
            party.is_client = payload.is_client
        customer_name = await self._customer_name(party.customer_id)
        return PartyDetail(party=party, customer_name=customer_name)

    async def remove_party(self, party: LawsuitParty) -> None:
        # Regra 1: o processo precisa ficar com no mínimo 1 parte.
        if await self.parties.count_for_lawsuit(party.lawsuit_id) <= 1:
            raise LastPartyError
        await self.parties.delete(party)

    async def list_timeline(
        self,
        lawsuit_id: uuid.UUID,
        *,
        kinds: Sequence[str],
        cursor: str | None,
        limit: int,
    ) -> TimelinePage:
        decoded = decode_timeline_cursor(cursor) if cursor else None
        items, total = await self.movements.list_timeline(
            lawsuit_id, kinds=kinds, cursor=decoded, limit=limit
        )
        next_cursor = (
            encode_timeline_cursor(items[-1].occurred_at, items[-1].kind, items[-1].id)
            if len(items) == limit
            else None
        )
        return TimelinePage(items=items, next_cursor=next_cursor, total=total)

    async def create_movement(
        self, lawsuit: Lawsuit, payload: MovementCreateRequest, author: User
    ) -> LawsuitMovement:
        return await self.movements.create(
            LawsuitMovement(
                tenant_id=self.tenant_id,
                lawsuit_id=lawsuit.id,
                origin=MovementOrigin.MANUAL,
                occurred_at=payload.occurred_at,
                title=payload.title,
                body=payload.body,
                created_by=author.id,
            )
        )

    def _check_movement_editable(self, movement: LawsuitMovement, actor: User) -> None:
        # Regra 3: movimentação do tribunal é imutável pela UI.
        if movement.origin != MovementOrigin.MANUAL:
            raise TribunalMovementImmutableError
        # Regra 4: só o autor ou um ADMINISTRADOR edita/exclui.
        if movement.created_by != actor.id and actor.role != UserRole.ADMINISTRADOR:
            raise MovementNotAuthorError

    async def update_movement(
        self, movement: LawsuitMovement, payload: MovementUpdateRequest, actor: User
    ) -> LawsuitMovement:
        self._check_movement_editable(movement, actor)
        movement.occurred_at = payload.occurred_at
        movement.title = payload.title
        movement.body = payload.body
        return movement

    async def delete_movement(self, movement: LawsuitMovement, actor: User) -> None:
        self._check_movement_editable(movement, actor)
        await self.movements.delete(movement)

    async def _validate_party_inputs(self, parties: Sequence[PartyInput]) -> None:
        seen: set[tuple[uuid.UUID, str]] = set()
        for party_input in parties:
            key = (party_input.customer_id, party_input.pole)
            if key in seen:
                raise DuplicatePartyError
            seen.add(key)
            if await self.customers.get_by_id(party_input.customer_id) is None:
                raise PartyCustomerNotFoundError

    async def _customer_name(self, customer_id: uuid.UUID) -> str:
        customer = await self.customers.get_by_id(customer_id)
        if customer is None:
            raise PartyCustomerNotFoundError
        return customer.name

    async def _ensure_not_duplicate(
        self,
        *,
        lawsuit_id: uuid.UUID,
        customer_id: uuid.UUID,
        pole: PartyPole,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        duplicate = await self.parties.find_duplicate(
            lawsuit_id=lawsuit_id, customer_id=customer_id, pole=pole, exclude_id=exclude_id
        )
        if duplicate is not None:
            raise DuplicatePartyError

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
