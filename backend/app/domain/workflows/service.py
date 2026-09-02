import uuid
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dates import add_business_days
from app.core.invariants import not_none
from app.domain.lawsuits.repository import LawsuitRepository
from app.domain.posts.models import Post
from app.domain.posts.repository import PostRepository
from app.domain.task_types.models import TaskType
from app.domain.task_types.repository import TaskTypeRepository
from app.domain.users.models import User
from app.domain.users.repository import UserRepository
from app.domain.workflows.models import Workflow, WorkflowStep
from app.domain.workflows.repository import HolidayRepository, WorkflowRepository


class WorkflowNameConflictError(Exception):
    """Nome já usado no tenant — 409."""


class WorkflowStepReferenceError(Exception):
    """Etapa aponta para tipo de tarefa ou usuário inexistente — 422."""


class InactiveAssigneeError(Exception):
    """Regra 5: responsável configurado ficou inativo → a aplicação INTEIRA falha
    (transacional — nenhuma tarefa é criada)."""


class AlreadyAppliedError(Exception):
    """Regra 8: reaplicar exige confirmação explícita do cliente — 409 sem ela."""


class LawsuitNotFoundError(Exception):
    """Processo fora do tenant (RLS) — 404."""


@dataclass
class PreviewTask:
    task_type_name: str
    user_id: uuid.UUID
    user_name: str
    date: date | None


@dataclass
class SkippedStep:
    task_type_name: str
    reason: str


@dataclass
class WorkflowPreview:
    tasks: list[PreviewTask] = field(default_factory=list)
    skipped: list[SkippedStep] = field(default_factory=list)
    already_applied: bool = False


@dataclass
class ApplyResult:
    created_ids: list[uuid.UUID]
    skipped: list[SkippedStep]


class WorkflowService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.workflows = WorkflowRepository(session)
        self.task_types = TaskTypeRepository(session)
        self.users = UserRepository(session)
        self.lawsuits = LawsuitRepository(session)
        self.posts = PostRepository(session)
        self.holidays = HolidayRepository(session)

    async def _validate_steps(
        self, steps: list[tuple[uuid.UUID, uuid.UUID | None, int | None]]
    ) -> None:
        for task_type_id, user_id, _offset in steps:
            if await self.task_types.get_by_id(task_type_id) is None:
                raise WorkflowStepReferenceError("Tipo de tarefa não encontrado.")
            if user_id is not None and await self.users.get_by_id(user_id) is None:
                raise WorkflowStepReferenceError("Usuário não encontrado.")

    def _build_steps(
        self, workflow_id: uuid.UUID, steps: list[tuple[uuid.UUID, uuid.UUID | None, int | None]]
    ) -> list[WorkflowStep]:
        """A posição é a ORDEM DO ARRAY — reordenar é só mandar a lista na nova ordem
        (regra 11) e o UNIQUE(workflow_id, position) nunca colide num replace atômico."""
        return [
            WorkflowStep(
                tenant_id=self.tenant_id,
                workflow_id=workflow_id,
                position=index,
                task_type_id=task_type_id,
                user_id=user_id,
                days_offset=days_offset,
            )
            for index, (task_type_id, user_id, days_offset) in enumerate(steps)
        ]

    async def create(
        self, name: str, steps: list[tuple[uuid.UUID, uuid.UUID | None, int | None]]
    ) -> Workflow:
        if await self.workflows.get_by_name(name) is not None:
            raise WorkflowNameConflictError(name)
        await self._validate_steps(steps)
        workflow = await self.workflows.create(Workflow(tenant_id=self.tenant_id, name=name))
        for step in self._build_steps(workflow.id, steps):
            self.session.add(step)
        await self.session.flush()
        return workflow

    async def update(
        self,
        workflow: Workflow,
        *,
        name: str,
        is_active: bool,
        steps: list[tuple[uuid.UUID, uuid.UUID | None, int | None]],
    ) -> Workflow:
        existing = await self.workflows.get_by_name(name)
        if existing is not None and existing.id != workflow.id:
            raise WorkflowNameConflictError(name)
        await self._validate_steps(steps)
        workflow.name = name
        workflow.is_active = is_active
        await self.workflows.replace_steps(workflow, self._build_steps(workflow.id, steps))
        return workflow

    async def _resolve_preview(
        self, workflow: Workflow, lawsuit_user_id: uuid.UUID, today: date
    ) -> tuple[
        list[PreviewTask], list[SkippedStep], list[tuple[WorkflowStep, TaskType, uuid.UUID]]
    ]:
        """O coração compartilhado de preview e apply (regra 6: o preview mostra
        EXATAMENTE o que o apply criaria — mesma resolução, mesma data base)."""
        steps = (await self.workflows.steps_for([workflow.id])).get(workflow.id, [])
        type_ids = {step.task_type_id for step in steps}
        types = {type_id: await self.task_types.get_by_id(type_id) for type_id in type_ids}
        user_ids = {step.user_id if step.user_id is not None else lawsuit_user_id for step in steps}
        names = await self.users.names_for(user_ids)
        holidays = await self.holidays.national_dates()

        tasks: list[PreviewTask] = []
        skipped: list[SkippedStep] = []
        effective: list[tuple[WorkflowStep, TaskType, uuid.UUID]] = []
        for step in steps:
            task_type = types[step.task_type_id]
            task_type = not_none(task_type, "FK validada no save")
            # Regra 10: tipo inativo é pulado, com aviso — não derruba a aplicação.
            if not task_type.is_active:
                skipped.append(
                    SkippedStep(task_type_name=task_type.name, reason="Tipo de tarefa inativo")
                )
                continue
            assignee_id = step.user_id if step.user_id is not None else lawsuit_user_id
            tasks.append(
                PreviewTask(
                    task_type_name=task_type.name,
                    user_id=assignee_id,
                    user_name=names.get(assignee_id, ""),
                    date=(
                        add_business_days(today, step.days_offset, holidays)
                        if step.days_offset is not None
                        else None
                    ),
                )
            )
            effective.append((step, task_type, assignee_id))
        return tasks, skipped, effective

    async def _already_applied(self, workflow: Workflow, lawsuit_id: uuid.UUID) -> bool:
        """Heurística da regra 8: já existe tarefa do processo com algum dos tipos do
        workflow — posts não guardam vínculo com o workflow (fora do modelo da spec)."""
        steps = (await self.workflows.steps_for([workflow.id])).get(workflow.id, [])
        type_ids = {step.task_type_id for step in steps}
        if not type_ids:
            return False
        existing = await self.posts.list_for_lawsuit(lawsuit_id)
        return any(post.task_type_id in type_ids for post in existing)

    async def preview(
        self, workflow: Workflow, lawsuit_id: uuid.UUID, today: date
    ) -> WorkflowPreview:
        lawsuit = await self.lawsuits.get_by_id(lawsuit_id)
        if lawsuit is None:
            raise LawsuitNotFoundError
        tasks, skipped, _effective = await self._resolve_preview(workflow, lawsuit.user_id, today)
        return WorkflowPreview(
            tasks=tasks,
            skipped=skipped,
            already_applied=await self._already_applied(workflow, lawsuit_id),
        )

    async def apply(
        self,
        workflow: Workflow,
        lawsuit_id: uuid.UUID,
        author: User,
        today: date,
        *,
        confirm_duplicate: bool,
    ) -> ApplyResult:
        """Regra 5: tudo numa transação — qualquer falha (responsável inativo, por
        exemplo) propaga exceção e a sessão da request rola INTEIRA, sem tarefa órfã."""
        lawsuit = await self.lawsuits.get_by_id(lawsuit_id)
        if lawsuit is None:
            raise LawsuitNotFoundError
        if not confirm_duplicate and await self._already_applied(workflow, lawsuit_id):
            raise AlreadyAppliedError
        _tasks, skipped, effective = await self._resolve_preview(workflow, lawsuit.user_id, today)

        created_ids: list[uuid.UUID] = []
        holidays = await self.holidays.national_dates()
        for step, task_type, assignee_id in effective:
            assignee = await self.users.get_by_id(assignee_id)
            if assignee is None or not assignee.is_active:
                raise InactiveAssigneeError(assignee_id)
            date_ = (
                add_business_days(today, step.days_offset, holidays)
                if step.days_offset is not None
                else None
            )
            post = Post(
                tenant_id=self.tenant_id,
                lawsuit_id=lawsuit_id,
                task_type_id=step.task_type_id,
                created_by=author.id,
                scheduled_date=date_,
                reward_snapshot=task_type.reward,
                show_in_schedule=task_type.show_in_schedule,
            )
            created = await self.posts.create_with_assignees(post, [assignee_id])
            created_ids.append(created.id)
        return ApplyResult(created_ids=created_ids, skipped=skipped)
