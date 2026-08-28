import uuid
from collections.abc import Sequence

from sqlalchemy import func, literal, select, update

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

    async def names_for(self, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        """Nomes de vários tipos em UMA query — a listagem de posts do processo (032)
        evita N+1 com ela."""
        if not ids:
            return {}
        stmt = select(TaskType.id, TaskType.name).where(TaskType.id.in_(ids))
        return {id_: str(name) for id_, name in await self.session.execute(stmt)}

    async def usage_count(self, task_type_id: uuid.UUID) -> int:
        """Quantas tarefas (posts) usam o tipo — plugado na tabela real na spec 032."""
        from app.domain.posts.models import Post

        stmt = select(func.count()).select_from(Post).where(Post.task_type_id == task_type_id)
        return int((await self.session.execute(stmt)).scalar_one())

    async def reassign(self, *, from_id: uuid.UUID, to_id: uuid.UUID) -> int:
        """Transferência em lote (regra 5 da 031) — UPDATE único nos posts."""
        from app.domain.posts.models import Post

        result = await self.session.execute(
            update(Post)
            .where(Post.task_type_id == from_id)
            .values(task_type_id=to_id)
            .execution_options(synchronize_session=False)
        )
        return int(result.rowcount)  # type: ignore[attr-defined]  # SQLAlchemy tipa `rowcount` só em `CursorResult`; um UPDATE/DELETE sempre devolve um.
