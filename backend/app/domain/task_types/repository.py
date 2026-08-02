import uuid
from collections.abc import Sequence

from sqlalchemy import func, literal, select

from app.core.repository import BaseRepository
from app.domain.task_types.models import TaskType


class TaskTypeRepository(BaseRepository[TaskType]):
    model = TaskType

    async def get_by_name(self, name: str) -> TaskType | None:
        """Regra 7: comparação sem acento e sem caso (immutable_unaccent da 014)."""
        result = await self.session.scalars(
            select(TaskType).where(
                func.immutable_unaccent(func.lower(TaskType.name))
                == func.immutable_unaccent(func.lower(literal(name)))
            )
        )
        return result.first()

    async def list_filtered(
        self,
        *,
        step_id: int | None,
        is_active: bool | None,
        query: str | None,
    ) -> Sequence[TaskType]:
        stmt = select(TaskType).order_by(func.lower(TaskType.name))
        if step_id is not None:
            stmt = stmt.where(TaskType.step_id == step_id)
        if is_active is not None:
            stmt = stmt.where(TaskType.is_active.is_(is_active))
        if query:
            pattern = func.concat("%", func.immutable_unaccent(func.lower(literal(query))), "%")
            stmt = stmt.where(func.immutable_unaccent(func.lower(TaskType.name)).ilike(pattern))
        return (await self.session.scalars(stmt)).all()

    async def usage_count(self, task_type_id: uuid.UUID) -> int:
        """Quantas tarefas usam o tipo — a tabela `tasks` só chega na spec 032; até lá
        nada pode estar "em uso" (regra 5 fica armada para a 032 plugar a contagem)."""
        return 0

    async def reassign(self, *, from_id: uuid.UUID, to_id: uuid.UUID) -> int:
        """Transferência em lote (regra 5) — idem: sem `tasks` até a 032, reatribui 0."""
        return 0
