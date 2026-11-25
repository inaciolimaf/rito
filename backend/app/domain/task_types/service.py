import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import Cache, invalidate, tenant_key
from app.core.transfer import validated_transfer
from app.domain.stages.repository import StepRepository
from app.domain.task_types.exceptions import (
    StepNotFoundError,
    SystemTaskTypeError,
    TaskTypeInUseError,
    TaskTypeNameAlreadyExistsError,
)
from app.domain.task_types.models import TaskType
from app.domain.task_types.repository import TaskTypeRepository
from app.domain.task_types.schemas import TaskTypeCreateRequest, TaskTypeUpdateRequest
from app.domain.task_types.score import suggest_reward


def catalog_cache_key(tenant_id: uuid.UUID) -> str:
    """Chave do catálogo completo do escritório (spec 098, regra 9)."""
    return tenant_key("task_types:catalog", tenant_id)


class TaskTypeService:
    def __init__(
        self, session: AsyncSession, tenant_id: uuid.UUID, *, cache: Cache | None = None
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.types = TaskTypeRepository(session)
        self.steps = StepRepository(session)
        # Spec 098, regra 9: escrita no catálogo derruba o cache da listagem.
        self.cache = cache

    async def invalidate_catalog(self) -> None:
        await invalidate(self.cache, catalog_cache_key(self.tenant_id))

    async def list_types(
        self, *, step_id: int | None, is_active: bool | None, query: str | None
    ) -> Sequence[tuple[TaskType, datetime | None]]:
        """O catálogo com a última atribuição (regra 9 da 031) de cada tipo.

        Vem em pares e não em duas chamadas porque a derivada é uma coluna da MESMA
        consulta: pedir a lista aqui e a data depois seria uma query por linha.
        """
        return await self.types.list_with_last_assigned(
            step_id=step_id, is_active=is_active, query=query
        )

    async def last_assigned_at(self, task_type_id: uuid.UUID) -> datetime | None:
        """A última atribuição de um tipo só — é o que POST e PUT devolvem, pelo mesmo
        caminho da listagem (regra 3 da spec 125)."""
        return await self.types.last_assigned_at(task_type_id)

    async def get(self, task_type_id: uuid.UUID) -> TaskType | None:
        return await self.types.get_by_id(task_type_id)

    async def _validate(self, payload: TaskTypeCreateRequest | TaskTypeUpdateRequest) -> None:
        if payload.step_id is not None and await self.steps.get_by_step_id(payload.step_id) is None:
            raise StepNotFoundError

    async def create(self, payload: TaskTypeCreateRequest) -> TaskType:
        await self._validate(payload)
        if await self.types.get_by_name(payload.name) is not None:
            raise TaskTypeNameAlreadyExistsError
        # Regra 2: sugestão da matriz, mas o valor informado vence.
        reward = payload.reward
        if reward is None:
            reward = (
                suggest_reward(payload.complexity, payload.duration)
                if payload.complexity is not None and payload.duration is not None
                else 0
            )
        task_type = TaskType(
            tenant_id=self.tenant_id,
            name=payload.name,
            step_id=payload.step_id,
            complexity=payload.complexity,
            duration=payload.duration,
            reward=reward,
            show_in_schedule=payload.show_in_schedule,
        )
        return await self.types.create(task_type)

    async def update(self, task_type: TaskType, payload: TaskTypeUpdateRequest) -> TaskType:
        await self._validate(payload)
        # Regra 4: sistêmica não pode ser renomeada — só a pontuação (e os demais
        # atributos) mudam.
        if task_type.is_system and payload.name != task_type.name:
            raise SystemTaskTypeError
        if payload.name != task_type.name:
            existing = await self.types.get_by_name(payload.name)
            if existing is not None and existing.id != task_type.id:
                raise TaskTypeNameAlreadyExistsError

        task_type.name = payload.name
        task_type.step_id = payload.step_id
        task_type.complexity = payload.complexity
        task_type.duration = payload.duration
        task_type.reward = payload.reward
        task_type.show_in_schedule = payload.show_in_schedule
        # Regra 6: inativar/restaurar preserva histórico e pontuação já creditada —
        # é só um flag, nunca um delete.
        task_type.is_active = payload.is_active
        return task_type

    async def delete(self, task_type: TaskType) -> None:
        # Regra 4: sistêmica nunca é excluída.
        if task_type.is_system:
            raise SystemTaskTypeError
        # Regra 5: tipo em uso exige transferência antes.
        if await self.types.usage_count(task_type.id) > 0:
            raise TaskTypeInUseError
        await self.types.delete(task_type)

    async def transfer(self, *, from_id: uuid.UUID, to_id: uuid.UUID) -> int:
        async def reassign() -> int:
            return await self.types.reassign(from_id=from_id, to_id=to_id)

        return await validated_transfer(
            from_id=from_id, to_id=to_id, get_by_id=self.types.get_by_id, reassign=reassign
        )
