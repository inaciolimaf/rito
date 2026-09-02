"""Workflow sugerido ao mover etapa (spec 053) — sugestão, aplicação com registro,
supressão e desfazer. A criação de tarefas em si é 100% de `WorkflowService` (spec
038, `app/domain/workflows/service.py`); este módulo só adiciona o que falta pro
gatilho de mover etapa: QUAL workflow sugerir, e um registro real (`workflow_
applications`) que permite desfazer — coisa que `WorkflowService` sozinho não tem
como fazer, já que `Post` não guarda vínculo com o workflow que o criou.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.lawsuits.exceptions import (
    WorkflowAlreadyAppliedError,
    WorkflowApplicationNotFoundError,
    WorkflowUndoHasCompletedTaskError,
    WorkflowUndoWindowExpiredError,
)
from app.domain.lawsuits.models import Lawsuit, WorkflowApplication, WorkflowSuppression
from app.domain.lawsuits.repository import (
    WorkflowApplicationRepository,
    WorkflowSuppressionRepository,
)
from app.domain.posts.repository import PostRepository
from app.domain.stages.models import Stage
from app.domain.stages.repository import StageRepository
from app.domain.users.models import User
from app.domain.workflows.models import Workflow
from app.domain.workflows.repository import WorkflowRepository
from app.domain.workflows.service import SkippedStep, WorkflowService

UNDO_WINDOW = timedelta(hours=1)  # regra 5


@dataclass
class ApplyOutcome:
    application: WorkflowApplication
    skipped: list[SkippedStep]


class LawsuitWorkflowService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.workflows = WorkflowRepository(session)
        self.applications = WorkflowApplicationRepository(session)
        self.suppressions = WorkflowSuppressionRepository(session)
        self.posts = PostRepository(session)
        self.stages = StageRepository(session)
        self.workflow_service = WorkflowService(session=session, tenant_id=tenant_id)

    async def get_workflow(self, workflow_id: uuid.UUID) -> Workflow | None:
        """De passagem (spec 118, checagem 2) — o router precisava do workflow para
        `apply` e ia buscá-lo no repositório."""
        return await self.workflows.get_by_id(workflow_id)

    async def suggest_for_stage_id(self, lawsuit: Lawsuit, stage_id: uuid.UUID) -> Workflow | None:
        """`suggest_for_move` a partir do id da etapa. Etapa inexistente devolve `None`
        — mesma resposta que o router dava ao não achar a etapa (spec 118, checagem 2)."""
        target_stage = await self.stages.get_by_id(stage_id)
        if target_stage is None:
            return None
        return await self.suggest_for_move(lawsuit, target_stage)

    async def suggest_for_move(self, lawsuit: Lawsuit, target_stage: Stage) -> Workflow | None:
        """Regra 1: sugere, nunca aplica sozinho. Regras 6/7: supressão é por
        processo+etapa, some ao voltar pra outra etapa e volta a valer se o processo
        retornar à mesma etapa depois."""
        if target_stage.suggested_workflow_id is None:
            return None
        if await self.suppressions.is_suppressed(lawsuit.id, target_stage.id):
            return None
        workflow = await self.workflows.get_by_id(target_stage.suggested_workflow_id)
        if workflow is None or not workflow.is_active:
            return None
        return workflow

    async def apply(
        self,
        lawsuit: Lawsuit,
        workflow: Workflow,
        actor: User,
        *,
        stage_id: uuid.UUID | None,
        confirm_duplicate: bool,
    ) -> ApplyOutcome:
        """Regra 8: "já aplicado" usa o registro REAL de `workflow_applications", não
        a heurística de `WorkflowService` (que só existe porque, antes desta spec,
        não havia de onde tirar essa informação)."""
        if not confirm_duplicate:
            latest = await self.applications.latest_for(lawsuit.id, workflow.id)
            if latest is not None:
                raise WorkflowAlreadyAppliedError(latest.applied_at)
        result = await self.workflow_service.apply(
            workflow, lawsuit.id, actor, datetime.now(UTC).date(), confirm_duplicate=True
        )
        application = WorkflowApplication(
            tenant_id=self.tenant_id,
            workflow_id=workflow.id,
            lawsuit_id=lawsuit.id,
            stage_id=stage_id,
            applied_by=actor.id,
            posts_created=result.created_ids,
        )
        created = await self.applications.create(application)
        return ApplyOutcome(application=created, skipped=result.skipped)

    async def suppress(self, lawsuit_id: uuid.UUID, stage_id: uuid.UUID) -> None:
        """Regra 6 — idempotente: repetir o "não sugerir mais" no mesmo par não quebra
        (UNIQUE já garante 1 linha; se já existe, não há o que fazer)."""
        if await self.suppressions.is_suppressed(lawsuit_id, stage_id):
            return
        await self.suppressions.create(
            WorkflowSuppression(tenant_id=self.tenant_id, lawsuit_id=lawsuit_id, stage_id=stage_id)
        )

    async def list_applications(
        self, lawsuit_id: uuid.UUID
    ) -> list[tuple[WorkflowApplication, str]]:
        applications = await self.applications.list_for_lawsuit(lawsuit_id)
        workflow_ids = {application.workflow_id for application in applications}
        names: dict[uuid.UUID, str] = {}
        if workflow_ids:
            stmt = select(Workflow.id, Workflow.name).where(Workflow.id.in_(workflow_ids))
            names = dict((await self.session.execute(stmt)).tuples().all())
        return [
            (application, names.get(application.workflow_id, "")) for application in applications
        ]

    async def undo(self, application: WorkflowApplication) -> None:
        """Regra 5: só em até 1 h e só se nenhuma tarefa criada foi concluída."""
        if datetime.now(UTC) - application.applied_at > UNDO_WINDOW:
            raise WorkflowUndoWindowExpiredError
        for post_id in application.posts_created:
            for line in await self.posts.lines_for_post(post_id):
                if line.completed_at is not None:
                    raise WorkflowUndoHasCompletedTaskError
        for post_id in application.posts_created:
            post = await self.posts.get_by_id(post_id)
            if post is not None:
                await self.posts.delete(post)
        await self.applications.delete(application)

    async def get_application(
        self, lawsuit_id: uuid.UUID, application_id: uuid.UUID
    ) -> WorkflowApplication:
        application = await self.applications.get_by_id(application_id)
        if application is None or application.lawsuit_id != lawsuit_id:
            raise WorkflowApplicationNotFoundError
        return application
