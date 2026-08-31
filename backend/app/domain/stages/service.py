import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.transfer import validated_transfer
from app.domain.stages.exceptions import (
    InvalidReorderError,
    StageInUseError,
    StageNameAlreadyExistsError,
    StepNotFoundError,
    SuggestedWorkflowNotFoundError,
)
from app.domain.stages.models import Stage, Step
from app.domain.stages.repository import StageRepository, StepRepository
from app.domain.stages.schemas import StageCreateRequest, StageUpdateRequest
from app.domain.workflows.repository import WorkflowRepository


class StepService:
    def __init__(self, session: AsyncSession) -> None:
        self.steps = StepRepository(session)

    async def list_steps(self) -> list[Step]:
        return list(await self.steps.list_all())


class StageService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.stages = StageRepository(session)
        self.steps = StepRepository(session)
        self.workflows = WorkflowRepository(session)

    async def _validate_suggested_workflow(self, workflow_id: uuid.UUID | None) -> None:
        if workflow_id is not None and await self.workflows.get_by_id(workflow_id) is None:
            raise SuggestedWorkflowNotFoundError

    async def list_stages(
        self, *, step_id: int | None, is_active: bool | None, query: str | None
    ) -> list[tuple[Stage, str]]:
        items = await self.stages.list_filtered(step_id=step_id, is_active=is_active, query=query)
        return [(stage, await self._step_name(stage.step_id)) for stage in items]

    async def get(self, stage_id: uuid.UUID) -> tuple[Stage, str] | None:
        stage = await self.stages.get_by_id(stage_id)
        if stage is None:
            return None
        return stage, await self._step_name(stage.step_id)

    async def create(self, payload: StageCreateRequest) -> tuple[Stage, str]:
        step_name = await self._step_name(payload.step_id)
        if await self.stages.get_by_name(step_id=payload.step_id, name=payload.name) is not None:
            raise StageNameAlreadyExistsError
        await self._validate_suggested_workflow(payload.suggested_workflow_id)

        position = await self.stages.next_position(payload.step_id)
        stage = Stage(
            tenant_id=self.tenant_id,
            step_id=payload.step_id,
            name=payload.name,
            position=position,
            enable_stagnant_days=payload.enable_stagnant_days,
            stagnant_days=payload.stagnant_days,
            suggested_workflow_id=payload.suggested_workflow_id,
        )
        created = await self.stages.create(stage)
        return created, step_name

    async def update(self, stage: Stage, payload: StageUpdateRequest) -> tuple[Stage, str]:
        step_name = await self._step_name(payload.step_id)
        changed_step = payload.step_id != stage.step_id
        if payload.name != stage.name or changed_step:
            existing = await self.stages.get_by_name(step_id=payload.step_id, name=payload.name)
            if existing is not None and existing.id != stage.id:
                raise StageNameAlreadyExistsError
        await self._validate_suggested_workflow(payload.suggested_workflow_id)

        if changed_step:
            # Mudou de fase: vai para o fim da nova fase, não herda a position da antiga
            # (regra 5 — position é um conceito local à fase).
            stage.position = await self.stages.next_position(payload.step_id)
        stage.name = payload.name
        stage.step_id = payload.step_id
        stage.enable_stagnant_days = payload.enable_stagnant_days
        stage.stagnant_days = payload.stagnant_days
        stage.suggested_workflow_id = payload.suggested_workflow_id
        stage.is_active = payload.is_active
        return stage, step_name

    async def delete(self, stage: Stage) -> None:
        # Regra 1 da 101: etapa com processo vinculado exige transferência antes.
        if await self.stages.usage_count(stage.id) > 0:
            raise StageInUseError
        await self.stages.delete(stage)

    async def reorder(self, stage_ids: list[uuid.UUID]) -> None:
        """Regra 5: ordenação é por `position` dentro da fase, reordenar é transacional."""
        found = await self.stages.get_many_by_id(stage_ids)
        by_id = {stage.id: stage for stage in found}
        if len(by_id) != len(stage_ids):
            raise InvalidReorderError
        if len({stage.step_id for stage in found}) > 1:
            raise InvalidReorderError

        for index, stage_id in enumerate(stage_ids, start=1):
            by_id[stage_id].position = index

    async def transfer(self, *, from_id: uuid.UUID, to_id: uuid.UUID) -> int:
        # Regra 2 da 101: reatribui os processos de verdade e devolve a contagem real.
        async def reassign() -> int:
            return await self.stages.reassign(from_id=from_id, to_id=to_id)

        return await validated_transfer(
            from_id=from_id, to_id=to_id, get_by_id=self.stages.get_by_id, reassign=reassign
        )

    async def _step_name(self, step_id: int) -> str:
        step = await self.steps.get_by_step_id(step_id)
        if step is None:
            raise StepNotFoundError
        return step.name
