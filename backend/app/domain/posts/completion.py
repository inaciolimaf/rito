"""Conclusão de posts (spec 040, alvo 2 — CompletePostUseCase): complete/reopen com
crédito de pontos congelado e disparo de recorrência, mais lida/estrela por usuário."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.automations.engine import AutomationEngine
from app.domain.automations.models import TriggerKind
from app.domain.posts.detail import PostDetail, build_detail
from app.domain.posts.exceptions import (
    CompleteForOthersForbiddenError,
    FutureCompletionError,
    NotAssigneeError,
)
from app.domain.posts.models import Post, PostUser
from app.domain.posts.recurrence_service import RecurrenceService
from app.domain.posts.repository import PostRepository
from app.domain.posts.schemas import PostCompleteRequest, PostReopenRequest
from app.domain.task_types.repository import TaskTypeRepository
from app.domain.users.models import User, UserRole

# Regra 9: ADMINISTRADOR (ou acima) pode concluir pela linha de outro responsável.
_ADMIN_OR_ABOVE = {UserRole.ADMINISTRADOR, UserRole.GESTOR}


class CompletePostUseCase:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.posts = PostRepository(session)
        self.task_types = TaskTypeRepository(session)
        self.recurrences = RecurrenceService(session, tenant_id)
        self.automations = AutomationEngine(session, tenant_id)

    async def _resolve_completion_line(
        self, post: Post, actor: User, target_user_id: uuid.UUID | None
    ) -> tuple[PostUser, bool]:
        """Targeting comum de complete/reopen: devolve (linha, por_terceiro)."""
        target_id = target_user_id or actor.id
        by_other = target_id != actor.id
        if by_other and actor.role not in _ADMIN_OR_ABOVE:
            # Regra 9: só ADMINISTRADOR+ conclui/reabre pela linha de outro.
            raise CompleteForOthersForbiddenError
        line = await self.posts.get_post_user(post.id, target_id)
        if line is None:
            # Regra 9: só quem é responsável tem linha para concluir.
            raise NotAssigneeError
        return line, by_other

    async def _detail(self, post: Post) -> PostDetail:
        return await build_detail(post, posts=self.posts, task_types=self.task_types)

    async def complete(self, post: Post, actor: User, payload: PostCompleteRequest) -> PostDetail:
        line, by_other = await self._resolve_completion_line(post, actor, payload.user_id)
        if line.completed_at is not None:
            return await self._detail(post)  # idempotente: já concluída, sem efeito
        completed_at = payload.completed_at or datetime.now(UTC)
        # Regra 4: retroativa permite o passado, NUNCA o futuro.
        if completed_at > datetime.now(UTC):
            raise FutureCompletionError
        line.completed_at = completed_at
        # Regra 2: os pontos creditados são o reward_snapshot do post — congelado ali.
        # Regra 5: retroativa credita na competência da data informada — completed_at
        # guarda a data informada, não "agora".
        line.points_earned = post.reward_snapshot
        # Regra 9: ADMIN concluindo por outro fica registrado em completed_by.
        line.completed_by = actor.id if by_other else None
        if post.recurrence_id is not None and await self.posts.all_completed(post.id):
            # Spec 034, regra 1: a série gera a próxima ocorrência ao concluir a
            # atual como um todo (todos os responsáveis).
            await self.recurrences.advance_on_completion(post)
        if await self.posts.all_completed(post.id):
            # Spec 092: a tarefa concluída é um dos 5 gatilhos, e é também o que acorda
            # quem esperava por ela (`after_previous`). Sem automação configurada isto é
            # um SELECT indexado e nada mais.
            await self.automations.emit(
                TriggerKind.TASK_COMPLETED.value,
                payload={
                    "post_id": str(post.id),
                    "lawsuit_id": str(post.lawsuit_id),
                    "task_type_id": str(post.task_type_id),
                    "completed_by": str(actor.id),
                },
                subject_type="post",
                subject_id=post.id,
            )
            await self.automations.resume_waiting_on(post.id)
        return await self._detail(post)

    async def reopen(self, post: Post, actor: User, payload: PostReopenRequest) -> PostDetail:
        line, _by_other = await self._resolve_completion_line(post, actor, payload.user_id)
        # Regra 6: reabrir zera conclusão e pontos daquele responsável.
        line.completed_at = None
        line.points_earned = None
        line.completed_by = None
        return await self._detail(post)

    async def set_read(self, post: Post, actor: User, *, value: bool) -> PostDetail:
        line = await self.posts.get_post_user(post.id, actor.id)
        if line is None:
            raise NotAssigneeError
        # Regra 11: lida é por usuário, não da tarefa.
        line.is_read = value
        return await self._detail(post)

    async def set_starred(self, post: Post, actor: User, *, value: bool) -> PostDetail:
        line = await self.posts.get_post_user(post.id, actor.id)
        if line is None:
            raise NotAssigneeError
        # Regra 11: estrela é por usuário, não da tarefa.
        line.is_starred = value
        return await self._detail(post)
