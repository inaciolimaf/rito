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
from app.ai.tools.write import Executed, WriteToolDef, get_write_tool
from app.core.invariants import not_none
from app.core.repository import BaseRepository
from app.domain.ai.models import AiAction, AiActionStatus, AiAuditLog
from app.domain.users.models import User

# Regra 4: proposta esquecida não fica pendurada.
ACTION_TTL = timedelta(hours=1)
# Regra 10: janela de desfazer.
UNDO_WINDOW = timedelta(minutes=5)
# Regra 12: enxurrada de aprovações é o mesmo que nenhuma aprovação — ninguém lê.
MAX_PENDING_PER_THREAD = 5
# O `model` da linha de auditoria do desfazer: não houve modelo nenhum, o gesto é humano.
# A coluna é `NOT NULL` e a resposta honesta para "qual modelo fez isso" é esta.
UNDO_MODEL = "humano (desfazer)"


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

    async def lock(self, action_id: uuid.UUID) -> AiAction | None:
        """Relê a ação com `SELECT … FOR UPDATE` e o estado que está no BANCO agora.

        Spec 133: `_ensure_pending` lia `status == "pending"` do objeto que a request já
        tinha em mãos. Em READ COMMITTED, dois `POST /approve` simultâneos (um duplo clique
        basta) liam os dois "pending", os dois passavam a guarda e os dois executavam — uma
        confirmação humana virando duas gravações de domínio e duas linhas em
        `ai_audit_log`, contra o §7.4 do `CLAUDE.md`.

        O `FOR UPDATE` faz a segunda request ESPERAR a primeira comitar, e o
        `populate_existing` é o que a obriga a enxergar o resultado: sem ele o SQLAlchemy
        devolveria o objeto do mapa de identidade, com o `pending` que ela leu antes de
        bloquear — a trava seguraria e a decisão continuaria sendo tomada sobre dado velho.
        """
        stmt = (
            select(AiAction)
            .where(AiAction.id == action_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return (await self.session.scalars(stmt)).first()

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

    async def _check_pending_limit(self, thread_id: uuid.UUID | None) -> None:
        """Uma conversa não acumula confirmações pendentes sem limite.

        Sem thread não há limite a checar: a ação veio de fora de uma conversa (worker,
        chamada avulsa) e não existe fila em que ela se empilhe.
        """
        if thread_id is None:
            return
        if await self.actions.count_pending_in_thread(thread_id) >= MAX_PENDING_PER_THREAD:
            raise TooManyPendingError

    async def _born_rejected(self, action: AiAction, motivo: str) -> AiAction:
        """Regra 6: sem permissão, a ação NASCE rejeitada — e mesmo assim é gravada.

        Gravar a tentativa é o ponto: é o que permite ao usuário ver que o agente quis fazer
        algo que ele não pode fazer. Apagar a tentativa esconderia justamente o caso que
        alguém precisa revisar.
        """
        action.preview = {"summary": motivo, "changes": {}}
        action.status = AiActionStatus.REJECTED.value
        action.rejection_reason = motivo
        action.decided_at = datetime.now(UTC)
        self.session.add(action)
        await self.session.flush()
        return action

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
        await self._check_pending_limit(ctx.thread_id)
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
            return await self._born_rejected(action, motivo)

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

    def _mark_executed(
        self,
        action: AiAction,
        executed: Executed,
        *,
        user: User,
        model: str,
    ) -> None:
        """Fecha a ação como executada e grava a trilha de auditoria (regra 7).

        Antes e depois no MESMO registro: sem o par, «a IA mudou o responsável» não diz de
        quem para quem, e a auditoria não serve para desfazer nem para explicar. O modelo e
        o thread entram junto porque a pergunta que se faz meses depois é «qual modelo fez
        isso, e em qual conversa».
        """
        action.status = AiActionStatus.EXECUTED.value
        action.affected_id = executed.affected_id
        action.executed_at = datetime.now(UTC)
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

    async def _execute_in_savepoint(
        self, definition: WriteToolDef, ctx: ToolContext, params: Any
    ) -> Any:
        """Regra 5: a execução passa pelo service do domínio, dentro de um SAVEPOINT.

        Validação que reprova humano reprova IA — e a reprovação vira `failed` com o motivo,
        não 500. O SAVEPOINT existe porque parte das validações só falha no banco (FK,
        constraint): sem ele, a transação abortada levaria junto o registro da própria
        falha, que é o que o usuário precisa ler.
        """
        async with self.session.begin_nested():
            return await definition.execute(ctx, params)

    async def approve(
        self, action: AiAction, *, user: User, model: str = "desconhecido"
    ) -> AiAction:
        """Regra 2: uma confirmação humana, uma execução, um registro.

        A guarda de estado roda sobre a linha TRAVADA (`actions.lock`), não sobre o objeto
        que a request carregava — é o que faz o segundo `approve` simultâneo virar 409 em
        vez de uma segunda gravação.

        E a permissão é reconferida AQUI, não só no `propose`. Entre propor e aprovar há o
        `ACTION_TTL` de uma hora, e o gestor que tira o acesso financeiro de alguém às 14h
        espera que a mudança valha às 14h01 — não que uma proposta das 13h30 continue
        executando com o crachá antigo.
        """
        self._ensure_owner(action, user)
        action = await self._locked_pending(action)
        definition = get_write_tool(action.tool_name)
        if definition is None:
            raise ActionNotPendingError
        motivo = _permission_error(definition, user)
        if motivo is not None:
            return await self._fail(action, motivo, user=user)

        params = definition.params_model.model_validate(action.arguments)
        action.status = AiActionStatus.APPROVED.value
        action.decided_by = user.id
        action.decided_at = datetime.now(UTC)
        try:
            executed = await self._execute_in_savepoint(
                definition, self._context_for(action, user), params
            )
        except Exception as exc:
            action.status = AiActionStatus.FAILED.value
            action.error = f"{type(exc).__name__}: {exc}"[:500]
            await self.session.flush()
            return action

        self._mark_executed(action, executed, user=user, model=model)
        await self.session.flush()
        return action

    def _context_for(self, action: AiAction, user: User) -> ToolContext:
        """O contexto em que a ferramenta roda: a sessão da request, o tenant e o usuário.

        Montado igual em `approve` e em `undo` — e é sempre o usuário LOGADO, nunca o que
        propôs, porque quem responde pela escrita é quem clicou.
        """
        return ToolContext(
            session=self.session,
            tenant_id=self.tenant_id,
            user=user,
            thread_id=action.thread_id,
        )

    async def reject(self, action: AiAction, *, user: User, reason: str | None) -> AiAction:
        self._ensure_owner(action, user)
        action = await self._locked_pending(action)
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
        travada = await self.actions.lock(action.id)
        if travada is None:  # pragma: no cover — a linha foi carregada nesta mesma sessão
            raise UndoNotAllowedError("A ação não existe mais.")
        action = travada
        self._ensure_undoable(action, agora)
        definition = self._undoable_tool(action, user)
        posterior = await self.audit.latest_for(action.affected_id) if action.affected_id else None
        if posterior is not None and posterior.action_id != action.id:
            raise UndoNotAllowedError("O registro foi alterado depois — desfazer sairia errado.")

        before = not_none(action.before_state, "garantido por _ensure_undoable")
        params = definition.params_model.model_validate({**action.arguments, **before})
        executed = await definition.execute(self._context_for(action, user), params)
        action.undone_at = agora
        self._log_undo(action, executed, user=user, anterior=posterior)
        await self.session.flush()
        return action

    async def _locked_pending(self, action: AiAction) -> AiAction:
        """A linha travada, e pendente segundo o BANCO — não segundo o objeto em memória."""
        travada = await self.actions.lock(action.id)
        if travada is None:  # pragma: no cover — carregada nesta mesma sessão logo acima
            raise ActionNotPendingError
        self._ensure_pending(travada)
        return travada

    async def _fail(self, action: AiAction, motivo: str, *, user: User) -> AiAction:
        """A ação decidida que não pode mais executar: `failed` com o motivo, sem
        `ai_audit_log` — nada foi gravado, e uma linha de auditoria aqui diria o contrário.
        """
        action.status = AiActionStatus.FAILED.value
        action.error = motivo[:500]
        action.decided_by = user.id
        action.decided_at = datetime.now(UTC)
        await self.session.flush()
        return action

    def _undoable_tool(self, action: AiAction, user: User) -> WriteToolDef:
        """A ferramenta do desfazer, com a permissão reconferida NO ATO.

        Desfazer é uma escrita de domínio igual à outra: quem perdeu o acesso entre executar
        e desfazer perdeu os dois lados da operação, não só um. A checagem só existia no
        `propose`, a uma hora de distância.
        """
        definition = get_write_tool(action.tool_name)
        if definition is None:
            raise UndoNotAllowedError("Ferramenta desconhecida.")
        motivo = _permission_error(definition, user)
        if motivo is not None:
            raise UndoNotAllowedError(motivo)
        return definition

    def _ensure_undoable(self, action: AiAction, agora: datetime) -> None:
        """As quatro razões pelas quais não se desfaz — a última é da spec 133.

        `undone_at` não era consultado em lugar nenhum: como o restore não gerava linha de
        auditoria, o guarda do `latest_for` continuava passando e o mesmo `undo` podia ser
        repetido dentro dos 5 minutos. Agora ele gera a linha E o estado é conferido, que é
        cinto sem suspensório: a linha nova aponta para a MESMA ação, então quem tem de
        barrar o segundo desfazer é o `undone_at`.
        """
        if action.status != AiActionStatus.EXECUTED.value or action.executed_at is None:
            raise UndoNotAllowedError("Só ação executada pode ser desfeita.")
        if action.undone_at is not None:
            raise UndoNotAllowedError("Esta ação já foi desfeita.")
        if agora - action.executed_at > UNDO_WINDOW:
            raise UndoNotAllowedError("A janela de 5 minutos para desfazer já passou.")
        if action.before_state is None:
            raise UndoNotAllowedError(
                "Criação não é desfeita pela IA — arquive o registro pela tela."
            )

    def _log_undo(
        self, action: AiAction, executed: Executed, *, user: User, anterior: AiAuditLog | None
    ) -> None:
        """O desfazer também é uma escrita, e escrita da IA vai para o `ai_audit_log`.

        Ele gravava só `undone_at` na própria ação — o §7.4 do `CLAUDE.md` («executa →
        grava em `ai_audit_log`») valia para a ida e não para a volta, e quem auditava
        seis meses depois via o registro voltar ao valor antigo sem nenhuma linha
        explicando quem mandou. O par antes/depois aqui é o inverso do da execução: sai do
        estado que a IA gravou e volta ao `before_state` original.
        """
        self.session.add(
            AiAuditLog(
                tenant_id=self.tenant_id,
                action_id=action.id,
                user_id=user.id,
                tool_name=f"{action.tool_name}:undo",
                affected_type=action.affected_type or "unknown",
                affected_id=executed.affected_id,
                before_state=anterior.after_state if anterior is not None else None,
                after_state=executed.after_state,
                model=UNDO_MODEL,
                thread_id=action.thread_id,
            )
        )

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
    """A recusa por perfil/acesso financeiro, na primeira pessoa de quem lê a tela.

    Spec 133: a tabela de ordem estava copiada aqui — a terceira cópia da mesma hierarquia,
    depois de `app/core/permissions.py` e `app/ai/tools/base.py`. Quem responde agora é a
    ferramenta; o que sobra é a frase, que é diferente porque o contexto é diferente: aqui
    a ação JÁ existe, e o usuário precisa ler por que ela não vai acontecer.
    """
    motivo = definition.permission_error(user)
    if motivo is None:
        return None
    return f"{motivo.rstrip('.')} — a ação foi recusada automaticamente."


def _jsonable(arguments: dict[str, Any]) -> dict[str, Any]:
    from datetime import date

    def convert(value: Any) -> Any:
        if isinstance(value, uuid.UUID | date | datetime):
            return str(value)
        if isinstance(value, list):
            return [convert(item) for item in value]
        return value

    return {key: convert(value) for key, value in arguments.items()}
