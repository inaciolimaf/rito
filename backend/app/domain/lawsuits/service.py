import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.action_groups.repository import ActionGroupRepository, LawsuitTypeRepository
from app.domain.courts.repository import CourtRepository
from app.domain.lawsuits.exceptions import (
    CourtSystemIncompatibleError,
    LawsuitTypeNotFoundError,
    ResponsibleNotActiveError,
    StageNotFoundError,
)
from app.domain.lawsuits.models import Lawsuit
from app.domain.lawsuits.repository import LawsuitRepository
from app.domain.lawsuits.schemas import LawsuitCreateRequest, LawsuitUpdateRequest
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

    async def get(self, lawsuit_id: uuid.UUID) -> LawsuitDetail | None:
        lawsuit = await self.lawsuits.get_by_id(lawsuit_id)
        if lawsuit is None:
            return None
        return await self._with_derived(lawsuit)

    async def create(self, payload: LawsuitCreateRequest) -> LawsuitDetail:
        await self._validate_references(payload)
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

    async def _validate_references(
        self, payload: LawsuitCreateRequest | LawsuitUpdateRequest
    ) -> None:
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
