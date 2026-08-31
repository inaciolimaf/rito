"""Casos de uso de thread de agente (spec 082).

O service cuida do que é regra de produto — de quem é o thread (regra 11), o que pode
ser retomado, o que pode ser cancelado — e delega a execução ao `GraphRuntime`.
"""

import uuid
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.graphs.base import GraphResult
from app.ai.graphs.registry import UnknownGraphError, get_graph
from app.ai.runtime import GraphRuntime, StepEvent
from app.core.http import get_or_404
from app.core.rls import set_tenant_context
from app.domain.ai.models import AiStep, AiThread, ThreadStatus
from app.domain.ai.repository import AiStepRepository, AiThreadRepository
from app.domain.users.models import User, UserRole

# Regra 4: espera humana expira em 24 h.
WAITING_EXPIRY_HOURS = 24
# Regra 12: thread concluído some depois de 90 dias.
THREAD_RETENTION_DAYS = 90

_RESUMABLE = {ThreadStatus.WAITING_HUMAN.value}
_CANCELLABLE = {
    ThreadStatus.PENDING.value,
    ThreadStatus.RUNNING.value,
    ThreadStatus.WAITING_HUMAN.value,
}


class ThreadNotResumableError(Exception):
    """Retomar thread que não está esperando ninguém → 409."""


class ThreadForbiddenError(Exception):
    """Regra 11: thread de outro usuário → 403 (ADMINISTRADOR passa, para auditar)."""


class AiThreadService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.threads = AiThreadRepository(session)
        self.steps = AiStepRepository(session)
        self.runtime = GraphRuntime(session, tenant_id)

    async def create(
        self,
        *,
        user: User,
        graph_name: str,
        title: str | None,
        context: dict[str, Any] | None,
    ) -> AiThread:
        graph = get_graph(graph_name)  # levanta UnknownGraphError → 422
        return await self.threads.create(
            AiThread(
                tenant_id=self.tenant_id,
                user_id=user.id,
                graph_name=graph.name,
                feature_key=graph.feature_key,
                title=title,
                context=context or {},
                status=ThreadStatus.PENDING.value,
            )
        )

    async def get_for(self, thread_id: uuid.UUID, user: User) -> AiThread:
        thread = await get_or_404(
            lambda: self.threads.get_by_id(thread_id), "Conversa de IA não encontrada."
        )
        self._ensure_visible(thread, user)
        return thread

    def _ensure_visible(self, thread: AiThread, user: User) -> None:
        """Regra 11: o thread é do usuário. ADMINISTRADOR (e GESTOR, pela hierarquia da
        spec 005) enxerga o dos outros — mas só para auditar, nunca para retomar."""
        if thread.user_id == user.id:
            return
        if user.role in (UserRole.ADMINISTRADOR, UserRole.GESTOR):
            return
        raise ThreadForbiddenError

    def _ensure_owner(self, thread: AiThread, user: User) -> None:
        """Agir no lugar do agente é do dono, e só dele: aprovar uma escrita que o
        agente propôs para OUTRA pessoa não é auditoria, é agir por ela."""
        if thread.user_id != user.id:
            raise ThreadForbiddenError

    async def run(self, thread: AiThread, input_: dict[str, Any]) -> GraphResult:
        return await self.runtime.start(thread, input_)

    async def stream(
        self, thread: AiThread, input_: dict[str, Any] | None
    ) -> AsyncIterator[StepEvent | GraphResult]:
        async for event in self.runtime.stream(thread, input_=input_):
            yield event

    async def resume(
        self,
        thread: AiThread,
        *,
        user: User,
        approved: bool,
        human_input: dict[str, Any] | None,
    ) -> GraphResult:
        self._ensure_owner(thread, user)
        if thread.status not in _RESUMABLE:
            raise ThreadNotResumableError(thread.status)
        return await self.runtime.resume(thread, approved=approved, human_input=human_input)

    async def cancel(self, thread: AiThread, user: User) -> AiThread:
        """Regra 6: marca a intenção; quem está executando para na próxima fronteira de
        nó. Cancelar o que já terminou não é erro — é no-op idempotente."""
        self._ensure_owner(thread, user)
        if thread.status in _CANCELLABLE:
            thread.status = ThreadStatus.CANCELLED.value
            thread.finished_at = datetime.now(UTC)
            thread.waiting_since = None
            await self.session.flush()
        return thread

    async def list_steps(self, thread: AiThread) -> Sequence[AiStep]:
        return await self.steps.list_for_thread(thread.id)

    async def expire_waiting(self, *, now: datetime | None = None) -> int:
        """Regra 4: quem esperou 24 h por uma confirmação que não veio é cancelado —
        thread pendurado indefinidamente vira lixo com estado sensível dentro."""
        cutoff = (now or datetime.now(UTC)) - timedelta(hours=WAITING_EXPIRY_HOURS)
        expired = await self.threads.list_waiting_since(cutoff)
        for thread in expired:
            thread.status = ThreadStatus.CANCELLED.value
            thread.error = "Expirou aguardando confirmação humana."
            thread.waiting_since = None
            thread.finished_at = datetime.now(UTC)
        await self.session.flush()
        return len(expired)


async def create_durable_thread(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user: User,
    tenant_id: uuid.UUID,
    graph_name: str,
    title: str | None,
    context: dict[str, Any] | None,
) -> uuid.UUID:
    """Cria o thread numa transação própria, que commita antes de ele rodar.

    Spec 103. Criar e executar na MESMA transação é o que tornava a dívida 21
    irrecuperável: se o timeout corta dentro de uma query, o registro da falha só pode
    ser escrito por outra conexão — e outra conexão não enxerga uma linha que ainda não
    foi comitada. Um thread que vai rodar existe antes de rodar; é isso, e só isso, que
    esta função garante.

    O efeito colateral é desejado: se o resto da requisição falhar, o thread continua
    lá, com o motivo. Antes, a execução sumia junto com a linha e o usuário ficava sem
    nada para olhar.
    """
    async with session_factory() as own, own.begin():
        await set_tenant_context(own, tenant_id)
        service = AiThreadService(own, tenant_id)
        thread = await service.create(
            user=user, graph_name=graph_name, title=title, context=context
        )
        await own.flush()
        return thread.id


__all__ = [
    "THREAD_RETENTION_DAYS",
    "WAITING_EXPIRY_HOURS",
    "AiThreadService",
    "ThreadForbiddenError",
    "ThreadNotResumableError",
    "UnknownGraphError",
    "create_durable_thread",
]
