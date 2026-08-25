"""Ciclo de vida das escritas propostas pela IA (spec 084).

O desenho todo existe para sustentar uma frase: **nada é gravado sem confirmação
humana explícita**. A ferramenta só sabe propor; quem executa é este service, depois de
um humano aprovar; e o que foi executado fica num log que o banco não deixa alterar.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.base import ToolContext
from app.ai.tools.write import WriteToolDef, get_write_tool
from app.core.repository import BaseRepository
from app.domain.ai.models import AiAction, AiActionStatus, AiAuditLog
from app.domain.users.models import User

# Regra 4: proposta esquecida não fica pendurada.
ACTION_TTL = timedelta(hours=1)
# Regra 10: janela de desfazer.
UNDO_WINDOW = timedelta(minutes=5)
# Regra 12: enxurrada de aprovações é o mesmo que nenhuma aprovação — ninguém lê.
MAX_PENDING_PER_THREAD = 5


class ActionNotPendingError(Exception):
    """Aprovar/rejeitar algo que já foi decidido (ou expirou) → 409."""


class ActionForbiddenError(Exception):
    """Regra 3: só o dono decide. Nem GESTOR aprova pelos outros."""


class TooManyPendingError(Exception):
    """Regra 12: seis propostas pendentes no mesmo thread."""


class UndoNotAllowedError(Exception):
    """Regra 10: fora da janela, sem estado anterior ou registro já alterado depois."""


class AiActionRepository(BaseRepository[AiAction]):
    model = AiAction

    async def list_for_user(
        self, *, user_id: uuid.UUID, status: str | None, limit: int
    ) -> Sequence[AiAction]:
        stmt = select(AiAction).where(AiAction.user_id == user_id)
        if status is not None:
            stmt = stmt.where(AiAction.status == status)
        return (
            await self.session.scalars(stmt.order_by(AiAction.created_at.desc()).limit(limit))
        ).all()

    async def count_pending_in_thread(self, thread_id: uuid.UUID) -> int:
        stmt = select(func.count()).where(
            AiAction.thread_id == thread_id, AiAction.status == AiActionStatus.PENDING.value
        )
        return int(await self.session.scalar(stmt) or 0)

    async def list_expired(self, now: datetime) -> Sequence[AiAction]:
        stmt = select(AiAction).where(
            AiAction.status == AiActionStatus.PENDING.value, AiAction.expires_at < now
        )
        return (await self.session.scalars(stmt)).all()


class AiAuditRepository(BaseRepository[AiAuditLog]):
    model = AiAuditLog

    async def list_for_record(
        self, *, affected_type: str | None, affected_id: uuid.UUID | None, limit: int
    ) -> Sequence[AiAuditLog]:
        stmt = select(AiAuditLog).order_by(AiAuditLog.created_at.desc()).limit(limit)
        if affected_type is not None:
            stmt = stmt.where(AiAuditLog.affected_type == affected_type)
        if affected_id is not None:
            stmt = stmt.where(AiAuditLog.affected_id == affected_id)
        return (await self.session.scalars(stmt)).all()

    async def latest_for(self, affected_id: uuid.UUID) -> AiAuditLog | None:
        stmt = (
            select(AiAuditLog)
            .where(AiAuditLog.affected_id == affected_id)
            .order_by(AiAuditLog.created_at.desc())
            .limit(1)
        )
        return (await self.session.scalars(stmt)).first()


class AiActionService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.actions = AiActionRepository(session)
        self.audit = AiAuditRepository(session)

    # ------------------------------------------------------------- propor

    async def propose(
        self,
        *,
        ctx: ToolContext,
        definition: WriteToolDef,
        arguments: dict[str, Any],
        model: str | None = None,
    ) -> AiAction:
        """Regra 1: chamar a ferramenta cria uma proposta e para por aí.

        Regra 6: sem permissão para a operação, a ação NASCE rejeitada — com o motivo
        registrado. Ela existe mesmo assim porque a tentativa é informação: é o que
        permite ao usuário ver que o agente quis fazer algo que ele não pode fazer.
        """
        if ctx.thread_id is not None:
            pendentes = await self.actions.count_pending_in_thread(ctx.thread_id)
            if pendentes >= MAX_PENDING_PER_THREAD:
                raise TooManyPendingError

        params = definition.params_model.model_validate(arguments)
        action = AiAction(
            tenant_id=self.tenant_id,
            thread_id=ctx.thread_id,
            user_id=ctx.user.id,
            tool_name=definition.name,
            arguments=_jsonable(arguments),
            preview={},
            expires_at=datetime.now(UTC) + ACTION_TTL,
        )

        motivo = _permission_error(definition, ctx.user)
        if motivo is not None:
            action.preview = {"summary": motivo, "changes": {}}
            action.status = AiActionStatus.REJECTED.value
            action.rejection_reason = motivo
            action.decided_at = datetime.now(UTC)
            self.session.add(action)
            await self.session.flush()
            return action

        proposal = await definition.preview(ctx, params)
        action.preview = proposal.to_preview()
        action.before_state = proposal.before_state
        action.affected_type = proposal.affected_type
        action.affected_id = proposal.affected_id
        if model:
            action.error = None
        self.session.add(action)
        await self.session.flush()
        return action

    # ------------------------------------------------------------- decidir

    async def approve(
        self, action: AiAction, *, user: User, model: str = "desconhecido"
    ) -> AiAction:
        self._ensure_owner(action, user)
        self._ensure_pending(action)
        definition = get_write_tool(action.tool_name)
        if definition is None:
            raise ActionNotPendingError

        ctx = ToolContext(
            session=self.session,
            tenant_id=self.tenant_id,
            user=user,
            thread_id=action.thread_id,
        )
        params = definition.params_model.model_validate(action.arguments)
        action.status = AiActionStatus.APPROVED.value
        action.decided_by = user.id
        action.decided_at = datetime.now(UTC)
        try:
            # Regra 5: a execução passa pelo service do domínio. Validação que reprova
            # humano reprova IA — e a reprovação vira `failed` com o motivo, não 500.
            #
            # O SAVEPOINT existe porque parte das validações só falha no banco (FK,
            # constraint): sem ele, a transação abortada levaria junto o registro da
            # própria falha, que é o que o usuário precisa ler.
            async with self.session.begin_nested():
                executed = await definition.execute(ctx, params)
        except Exception as exc:
            action.status = AiActionStatus.FAILED.value
            action.error = f"{type(exc).__name__}: {exc}"[:500]
            await self.session.flush()
            return action

        action.status = AiActionStatus.EXECUTED.value
        action.affected_id = executed.affected_id
        action.executed_at = datetime.now(UTC)
        # Regra 7: o que a IA gravou, com antes e depois, o modelo e o thread.
        self.session.add(
            AiAuditLog(
                tenant_id=self.tenant_id,
                action_id=action.id,
                user_id=user.id,
                tool_name=action.tool_name,
                affected_type=action.affected_type or "unknown",
                affected_id=executed.affected_id,
                before_state=action.before_state,
                after_state=executed.after_state,
                model=model,
                thread_id=action.thread_id,
            )
        )
        await self.session.flush()
        return action

    async def reject(self, action: AiAction, *, user: User, reason: str | None) -> AiAction:
        self._ensure_owner(action, user)
        self._ensure_pending(action)
        action.status = AiActionStatus.REJECTED.value
        action.rejection_reason = reason or "Recusado pelo usuário."
        action.decided_by = user.id
        action.decided_at = datetime.now(UTC)
        await self.session.flush()
        return action

    async def undo(self, action: AiAction, *, user: User, now: datetime | None = None) -> AiAction:
        """Regra 10: desfazer é do HUMANO, dentro de 5 minutos, e só se ninguém mexeu
        no registro depois.

        Criação não se desfaz aqui: a IA não apaga (regra 13), e apagar em nome dela
        seria o mesmo efeito por outro caminho. Para criação, o caminho é arquivar pela
        tela — decisão explícita de uma pessoa, com o registro preservado.
        """
        self._ensure_owner(action, user)
        agora = now or datetime.now(UTC)
        if action.status != AiActionStatus.EXECUTED.value or action.executed_at is None:
            raise UndoNotAllowedError("Só ação executada pode ser desfeita.")
        if agora - action.executed_at > UNDO_WINDOW:
            raise UndoNotAllowedError("A janela de 5 minutos para desfazer já passou.")
        if action.before_state is None:
            raise UndoNotAllowedError(
                "Criação não é desfeita pela IA — arquive o registro pela tela."
            )
        posterior = await self.audit.latest_for(action.affected_id) if action.affected_id else None
        if posterior is not None and posterior.action_id != action.id:
            raise UndoNotAllowedError("O registro foi alterado depois — desfazer sairia errado.")

        definition = get_write_tool(action.tool_name)
        if definition is None:
            raise UndoNotAllowedError("Ferramenta desconhecida.")
        ctx = ToolContext(
            session=self.session,
            tenant_id=self.tenant_id,
            user=user,
            thread_id=action.thread_id,
        )
        restore_args = {**action.arguments, **action.before_state}
        params = definition.params_model.model_validate(restore_args)
        await definition.execute(ctx, params)
        action.undone_at = agora
        await self.session.flush()
        return action

    async def expire_pending(self, *, now: datetime | None = None) -> int:
        """Regra 4."""
        agora = now or datetime.now(UTC)
        expiradas = await self.actions.list_expired(agora)
        for action in expiradas:
            action.status = AiActionStatus.EXPIRED.value
            action.decided_at = agora
        await self.session.flush()
        return len(expiradas)

    # ------------------------------------------------------------- guardas

    def _ensure_owner(self, action: AiAction, user: User) -> None:
        """Regra 3: aprovar é assinar embaixo. Perfil de gestão não transfere isso."""
        if action.user_id != user.id:
            raise ActionForbiddenError

    def _ensure_pending(self, action: AiAction) -> None:
        if action.status != AiActionStatus.PENDING.value:
            raise ActionNotPendingError
        if action.expires_at < datetime.now(UTC):
            action.status = AiActionStatus.EXPIRED.value
            raise ActionNotPendingError


def _permission_error(definition: WriteToolDef, user: User) -> str | None:
    from app.core.permissions import FinancialAccess, UserRole

    role_order = {UserRole.COLABORADOR: 0, UserRole.ADMINISTRADOR: 1, UserRole.GESTOR: 2}
    financial_order = {
        FinancialAccess.NONE: 0,
        FinancialAccess.READ_ONLY: 1,
        FinancialAccess.FULL: 2,
    }
    if role_order[user.role] < role_order[definition.requires_role]:
        return (
            f"O usuário não tem perfil {definition.requires_role.value} para "
            f"{definition.name} — a ação foi recusada automaticamente."
        )
    if financial_order[user.financial_access] < financial_order[definition.requires_financial]:
        return (
            f"O usuário não tem acesso financeiro suficiente para {definition.name} — "
            "a ação foi recusada automaticamente."
        )
    return None


def _jsonable(arguments: dict[str, Any]) -> dict[str, Any]:
    from datetime import date

    def convert(value: Any) -> Any:
        if isinstance(value, uuid.UUID | date | datetime):
            return str(value)
        if isinstance(value, list):
            return [convert(item) for item in value]
        return value

    return {key: convert(value) for key, value in arguments.items()}
