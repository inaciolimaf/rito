"""Auditoria de chamadas externas (spec 041, regra 6 e §4).

Toda falha é gravada em `external_requests`; sucesso é amostrado (o volume de
sucesso não justifica uma linha por chamada — o painel de 049 se importa com
falha e latência). A escrita NUNCA pode derrubar a chamada: um sink quebrado
vira log de warning e a resposta segue.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.external_requests.models import ExternalRequest

logger = logging.getLogger("rito.http")


@dataclass
class RequestAuditEntry:
    tenant_id: uuid.UUID | None  # nulo em chamada de sistema (worker, sem tenant)
    host: str
    method: str
    path: str
    status_code: int | None
    duration_ms: int
    attempt: int
    error: str | None


class AuditSink(Protocol):
    async def record(self, entry: RequestAuditEntry) -> None: ...


class NullAuditSink:
    async def record(self, entry: RequestAuditEntry) -> None:
        pass


class DbAuditSink:
    """Grava em `external_requests` numa sessão própria, independente da request.

    A sessão é aberta por registro (e não reutilizada) porque a chamada externa
    costuma acontecer fora do ciclo de request do FastAPI — num worker Celery,
    sem sessão de banco à mão.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def record(self, entry: RequestAuditEntry) -> None:
        async with self._session_factory() as session, session.begin():
            if entry.tenant_id is not None:
                await set_tenant_context(session, entry.tenant_id)
            session.add(
                ExternalRequest(
                    tenant_id=entry.tenant_id,
                    host=entry.host,
                    method=entry.method,
                    path=entry.path,
                    status_code=entry.status_code,
                    duration_ms=entry.duration_ms,
                    attempt=entry.attempt,
                    error=entry.error,
                )
            )


class SafeAuditSink:
    """Envolve o sink real: falha de auditoria vira warning, nunca quebra a chamada."""

    def __init__(self, inner: AuditSink) -> None:
        self._inner = inner

    async def record(self, entry: RequestAuditEntry) -> None:
        try:
            await self._inner.record(entry)
        except Exception:
            logger.warning(
                "falha ao auditar chamada externa host=%s path=%s",
                entry.host,
                entry.path,
                exc_info=True,
            )
