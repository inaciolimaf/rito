"""Guarda da regra 5 (excluir tipo em uso exige transferência) testada na unidade: a
tabela `tasks` só chega na 032, então a integração não consegue criar o cenário — o
fake do repositório (uma implementação real do contrato, LSP) simula o tipo em uso."""

import uuid

import pytest

from app.domain.task_types.exceptions import TaskTypeInUseError
from app.domain.task_types.models import TaskType
from app.domain.task_types.service import TaskTypeService


class _InUseRepository:
    """Fake mínimo do contrato usado por `delete` — tipo com 3 tarefas vinculadas."""

    async def usage_count(self, task_type_id: uuid.UUID) -> int:
        return 3

    async def delete(self, task_type: TaskType) -> None:  # pragma: no cover
        raise AssertionError("não deveria chegar a excluir")


async def test_excluir_tipo_em_uso_levanta_in_use() -> None:
    service = TaskTypeService(session=None, tenant_id=uuid.uuid4())  # type: ignore[arg-type]
    service.types = _InUseRepository()  # type: ignore[assignment]

    task_type = TaskType(tenant_id=uuid.uuid4(), name="Em uso", reward=0)
    with pytest.raises(TaskTypeInUseError):
        await service.delete(task_type)
