import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.action_groups.repository import ActionGroupRepository, LawsuitTypeRepository
from app.domain.courts.repository import CourtRepository
from app.domain.customers.repository import CustomerRepository
from app.domain.lawsuits.exceptions import (
    CourtSystemIncompatibleError,
    DuplicatePartyError,
    LastPartyError,
    LawsuitTypeNotFoundError,
    PartyCustomerNotFoundError,
    ResponsibleNotActiveError,
    StageNotFoundError,
)
from app.domain.lawsuits.models import Lawsuit, LawsuitParty, PartyPole
from app.domain.lawsuits.repository import LawsuitPartyRepository, LawsuitRepository
from app.domain.lawsuits.schemas import (
    LawsuitBaseRequest,
    LawsuitCreateRequest,
    LawsuitUpdateRequest,
    PartyCreateRequest,
    PartyInput,
    PartyUpdateRequest,
)
from app.domain.stages.repository import StageRepository, StepRepository
from app.domain.users.repository import UserRepository


def _only_digits(value: str | None) -> str | None:
    """Regra 6: `process_number` guardado só com dígitos — a máscara é de apresentação."""
    if value is None:
        return None
    digits = "".join(character for character in value if character.isdigit())
    return digits or None


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
            process_number=_only_digits(payload.process_number),
            protocol_number=payload.protocol_number,
            originating_process=payload.originating_process,
            folder=payload.folder,
            filing_year=payload.filing_year,
            judiciary=payload.judiciary,
            county=payload.county,
            court_division=payload.court_division,
            process_date=payload.process_date,
            notes=payload.notes,
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
        lawsuit.process_number = _only_digits(payload.process_number)
        lawsuit.protocol_number = payload.protocol_number
        lawsuit.originating_process = payload.originating_process
        lawsuit.folder = payload.folder
        lawsuit.filing_year = payload.filing_year
        lawsuit.judiciary = payload.judiciary
        lawsuit.county = payload.county
        lawsuit.court_division = payload.court_division
        lawsuit.process_date = payload.process_date
        lawsuit.notes = payload.notes
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
