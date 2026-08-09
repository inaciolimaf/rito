import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import BaseRepository
from app.domain.workflows.models import Holiday, Workflow, WorkflowStep


class WorkflowRepository(BaseRepository[Workflow]):
    model = Workflow

    async def list_filtered(
        self, *, status: str | None, q: str | None
    ) -> Sequence[tuple[Workflow, int]]:
        """Workflows com a contagem de etapas na MESMA query (sem N+1)."""
        step_count = (
            select(func.count(WorkflowStep.id))
            .where(WorkflowStep.workflow_id == Workflow.id)
            .correlate(Workflow)
            .scalar_subquery()
        )
        stmt = select(Workflow, step_count).order_by(Workflow.name)
        if status == "active":
            stmt = stmt.where(Workflow.is_active.is_(True))
        elif status == "inactive":
            stmt = stmt.where(Workflow.is_active.is_(False))
        if q:
            stmt = stmt.where(Workflow.name.ilike(f"%{q}%"))
        result = await self.session.execute(stmt)
        return [(workflow, count) for workflow, count in result.all()]

    async def get_by_name(self, name: str) -> Workflow | None:
        stmt = select(Workflow).where(Workflow.name == name)
        return (await self.session.scalars(stmt)).first()

    async def steps_for(
        self, workflow_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[WorkflowStep]]:
        if not workflow_ids:
            return {}
        stmt = (
            select(WorkflowStep)
            .where(WorkflowStep.workflow_id.in_(workflow_ids))
            .order_by(WorkflowStep.position)
        )
        result: dict[uuid.UUID, list[WorkflowStep]] = {wid: [] for wid in workflow_ids}
        for step in (await self.session.scalars(stmt)).all():
            result[step.workflow_id].append(step)
        return result

    async def replace_steps(self, workflow: Workflow, steps: Sequence[WorkflowStep]) -> None:
        """PUT reconcilia o conjunto inteiro (regra 11: transacional — mesma sessão
        da request; falha no meio, tudo rola junto)."""
        await self.session.execute(
            sql_delete(WorkflowStep).where(WorkflowStep.workflow_id == workflow.id)
        )
        for step in steps:
            self.session.add(step)
        await self.session.flush()


class HolidayRepository:
    """Leitura da tabela global de feriados (sem tenant/RLS)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_dates(self, *, year: int | None = None) -> Sequence[Holiday]:
        # A coluna `date` está mapeada no atributo `id` (ver models.Holiday).
        stmt = select(Holiday).order_by(Holiday.id)
        if year is not None:
            stmt = stmt.where(Holiday.id >= date(year, 1, 1), Holiday.id <= date(year, 12, 31))
        return (await self.session.scalars(stmt)).all()

    async def national_dates(self) -> set[date]:
        stmt = select(Holiday.id).where(Holiday.is_national.is_(True))
        return set((await self.session.scalars(stmt)).all())
