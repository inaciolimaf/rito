import uuid
from collections.abc import Sequence

from sqlalchemy import func, select, update

from app.core.repository import BaseRepository
from app.domain.stages.models import Stage, Step


class StepRepository(BaseRepository[Step]):
    model = Step

    async def list_all(self) -> Sequence[Step]:
        result = await self.session.scalars(select(Step).order_by(Step.position))
        return result.all()

    async def get_by_step_id(self, id_: int) -> Step | None:
        # BaseRepository.get_by_id espera uuid.UUID (toda outra tabela usa PK UUID) —
        # steps é PK inteira (mesma exceção documentada em Occupation, spec 012), daí um
        # método com nome próprio em vez de sobrescrever get_by_id com tipo incompatível.
        return await self.session.get(Step, id_)


class StageRepository(BaseRepository[Stage]):
    model = Stage

    async def get_by_name(self, *, step_id: int, name: str) -> Stage | None:
        """Regra 6: nome único por (tenant, fase) — a mesma fonte real repete
        "PLANEJAMENTO" em fases diferentes, então a checagem de duplicidade é por fase."""
        result = await self.session.scalars(
            select(Stage).where(
                Stage.step_id == step_id,
                func.unaccent(func.lower(Stage.name)) == func.unaccent(func.lower(name)),
            )
        )
        return result.first()

    async def next_position(self, step_id: int) -> int:
        """Nova etapa entra no fim da fase — sem isso, toda etapa nasceria com
        `position=0` e a ordem entre etapas recém-criadas ficaria indefinida (a cargo do
        Postgres, não da regra 5)."""
        current_max = await self.session.scalar(
            select(func.max(Stage.position)).where(Stage.step_id == step_id)
        )
        return (current_max or 0) + 1

    async def list_filtered(
        self,
        *,
        step_id: int | None = None,
        is_active: bool | None = None,
        query: str | None = None,
    ) -> Sequence[Stage]:
        stmt = select(Stage).order_by(Stage.step_id, Stage.position, Stage.id)
        if step_id is not None:
            stmt = stmt.where(Stage.step_id == step_id)
        if is_active is not None:
            stmt = stmt.where(Stage.is_active.is_(is_active))
        if query:
            stmt = stmt.where(Stage.name.ilike(f"%{query}%"))
        return (await self.session.scalars(stmt)).all()

    async def get_many_by_id(self, stage_ids: list[uuid.UUID]) -> Sequence[Stage]:
        return (await self.session.scalars(select(Stage).where(Stage.id.in_(stage_ids)))).all()

    async def usage_count(self, stage_id: uuid.UUID) -> int:
        """Quantos processos estão na etapa (spec 101, regra 1). `lawsuits.stage_id` é FK
        NOT NULL desde a 022 — não existe processo "sem etapa" para onde escorregar."""
        from app.domain.lawsuits.models import Lawsuit

        stmt = select(func.count()).select_from(Lawsuit).where(Lawsuit.stage_id == stage_id)
        return int((await self.session.execute(stmt)).scalar_one())

    async def reassign(self, *, from_id: uuid.UUID, to_id: uuid.UUID) -> int:
        """Transferência em lote (spec 101, regra 2) — UPDATE único nos processos, mesmo
        formato de TaskTypeRepository.reassign (031)."""
        from app.domain.lawsuits.models import Lawsuit

        result = await self.session.execute(
            update(Lawsuit)
            .where(Lawsuit.stage_id == from_id)
            .values(stage_id=to_id)
            .execution_options(synchronize_session=False)
        )
        return int(result.rowcount)  # type: ignore[attr-defined]  # SQLAlchemy tipa `rowcount` só em `CursorResult`; um UPDATE sempre devolve um.
