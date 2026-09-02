"""Copiloto global (spec 085).

A conversa em si: recebe a pergunta, monta o estado com o histórico e o contexto da
tela, roda o grafo base (082) com as ferramentas (083/084) e devolve o que aconteceu —
inclusive a ação que ficou esperando confirmação.

Nada aqui decide o que o agente faz; isso é do grafo. O que mora neste service são as
regras da CONVERSA: contexto de tela, limite de mensagens, o que pode ser persistido e
o que o usuário vê quando algo falha.
"""

import uuid
from collections.abc import AsyncIterator, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.graphs.base import GraphDeps, GraphResult
from app.ai.runtime import GraphRuntime, StepEvent
from app.ai.tools.base import ToolContext, tool_specs
from app.ai.tools.runner import ToolRunner
from app.core.repository import BaseRepository
from app.domain.ai.exceptions import FeatureDisabledError
from app.domain.ai.models import AiMessage, AiThread, ThreadStatus
from app.domain.ai.service import AiConfigService, AiRunner
from app.domain.ai.threads import AiThreadService, create_durable_thread
from app.domain.users.models import User
from app.integrations.openrouter.types import LLMNotConfiguredError, LLMProvider

COPILOT_FEATURE = "copilot"
COPILOT_GRAPH = "base_agent"
# Regra 8: conversa muito longa fica cara e pior — melhor recomeçar com o contexto limpo.
MAX_MESSAGES_PER_THREAD = 50
# Regra 6: o título sai da primeira pergunta.
TITLE_MAX_CHARS = 60
# Regra 7.
ARCHIVE_AFTER_DAYS = 30

# Regra 3: nome de ferramenta é jargão; a UI mostra isto.
TOOL_LABELS: dict[str, str] = {
    "search_customers": "consultando contatos",
    "get_customer": "abrindo a ficha do contato",
    "search_lawsuits": "consultando processos",
    "get_lawsuit": "abrindo o processo",
    "get_lawsuit_timeline": "lendo o andamento do processo",
    "search_tasks": "consultando tarefas",
    "get_inbox": "olhando a caixa de entrada",
    "search_publications": "consultando intimações",
    "get_publication": "lendo a intimação",
    "search_transactions": "verificando o financeiro",
    "get_financial_summary": "conferindo o caixa",
    "get_lawsuit_financials": "conferindo o financeiro do processo",
    "get_productivity": "consultando a produtividade",
    "get_bi_metrics": "consultando os indicadores",
    "list_taxonomies": "consultando as configurações do escritório",
    "get_current_context": "conferindo a tela aberta",
}

# Regra 5: a sugestão útil depende de onde a pessoa está.
_SUGGESTIONS_BY_ROUTE: dict[str, tuple[str, ...]] = {
    "/lawsuits": ("Resumir o andamento deste processo", "Quais prazos estão próximos?"),
    "/customers": ("Quanto esse cliente deve?", "Quais processos esse cliente tem?"),
    "/transactions": ("Quem está inadimplente?", "Como está o caixa deste mês?"),
    "/home": ("O que é mais urgente hoje?", "Quais tarefas vencem esta semana?"),
    "/publications": ("Resumir as intimações de hoje", "Quais intimações ainda não li?"),
    "/reports": ("Como está a produtividade do time?", "Qual a taxa de sucesso do escritório?"),
}
_DEFAULT_SUGGESTIONS = (
    "O que é mais urgente hoje?",
    "Buscar um processo pelo número",
    "Resumir a semana do escritório",
)


class ThreadLimitReachedError(Exception):
    """Regra 8: passou de 50 mensagens — a resposta é sugerir uma conversa nova."""


class CopilotUnavailableError(Exception):
    """Regra 10: sem chave ou com a feature desligada, o copiloto não existe na UI."""


@dataclass
class CopilotTurn:
    thread: AiThread
    reply: str | None = None
    pending_action: dict[str, Any] | None = None
    tool_labels: list[str] = field(default_factory=list)
    error: str | None = None


class AiMessageRepository(BaseRepository[AiMessage]):
    model = AiMessage

    async def list_for_thread(self, thread_id: uuid.UUID) -> Sequence[AiMessage]:
        stmt = (
            select(AiMessage)
            .where(AiMessage.thread_id == thread_id)
            .order_by(AiMessage.created_at, AiMessage.id)
        )
        return (await self.session.scalars(stmt)).all()

    async def count_for_thread(self, thread_id: uuid.UUID) -> int:
        stmt = select(func.count()).where(AiMessage.thread_id == thread_id)
        return int(await self.session.scalar(stmt) or 0)


class CopilotService:
    def __init__(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        provider: LLMProvider,
        *,
        thread_sessions: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.provider = provider
        # Spec 103: fábrica de sessão para criar o thread de forma durável ANTES de ele
        # rodar. Nula onde nada roda (listar, ler, apagar) — só quem executa precisa.
        self.thread_sessions = thread_sessions
        self.messages = AiMessageRepository(session)
        self.threads = AiThreadService(session, tenant_id)
        self.config = AiConfigService(session, tenant_id)

    # ------------------------------------------------------------ disponibilidade

    async def ensure_available(self) -> None:
        """Regra 10: a checagem é uma só, e vale para a UI e para a API."""
        if not getattr(self.provider, "is_configured", False):
            raise CopilotUnavailableError("Nenhuma chave de IA configurada no servidor.")
        feature = await self.config.resolve(COPILOT_FEATURE)
        if not feature.is_enabled:
            raise CopilotUnavailableError("O copiloto está desligado para este escritório.")

    def suggestions(self, route: str | None) -> list[str]:
        """Regra 5."""
        if route:
            for prefix, items in _SUGGESTIONS_BY_ROUTE.items():
                if route.startswith(prefix):
                    return list(items)
        return list(_DEFAULT_SUGGESTIONS)

    # ------------------------------------------------------------------ conversa

    async def start_turn(
        self,
        *,
        user: User,
        thread_id: uuid.UUID | None,
        message: str,
        context: dict[str, Any] | None,
        model: str | None = None,
    ) -> tuple[AiThread, dict[str, Any]]:
        """Prepara o turno: acha (ou cria) o thread, guarda a pergunta e monta o estado.

        Separado de `run_turn` porque o SSE precisa do thread ANTES de começar a rodar —
        é o que permite o cliente ver o primeiro passo em vez de esperar a resposta
        inteira.
        """
        await self.ensure_available()
        thread = await self._resolve_thread(user, thread_id, message, context, model)
        if await self.messages.count_for_thread(thread.id) >= MAX_MESSAGES_PER_THREAD:
            raise ThreadLimitReachedError
        feature = await self.config.resolve(COPILOT_FEATURE)
        historico = await self._history_state(thread, store=feature.store_prompts)
        self.session.add(
            AiMessage(
                tenant_id=self.tenant_id,
                thread_id=thread.id,
                role="user",
                # Regra 13: sem opt-in, a linha guarda só o metadado.
                content=message if feature.store_prompts else None,
            )
        )
        await self.session.flush()
        state = {
            "input": {"question": message},
            "messages": historico,
            "scratch": {},
        }
        return thread, state

    async def run_turn(self, *, user: User, thread: AiThread, state: dict[str, Any]) -> CopilotTurn:
        turn = CopilotTurn(thread=thread)
        async for event in self._drive(user, thread, state):
            self._absorb(turn, event)
        await self._persist_reply(thread, turn)
        return turn

    def _eventos_do_progresso(
        self, turn: CopilotTurn, event: StepEvent | GraphResult
    ) -> Iterator[tuple[str, dict[str, Any]]]:
        """O que vai para a tela ENQUANTO o grafo anda (regra 2).

        Separado de `stream_turn` na spec 106: aquele método cuida do turno inteiro —
        abrir, absorver, persistir, fechar —, e este só traduz um evento do grafo em zero
        ou mais eventos de SSE. A resposta final não sai daqui de propósito: ela só existe
        depois de `_persist_reply`, e emiti-la no laço seria dizer que ficou pronta antes
        de estar gravada.
        """
        if isinstance(event, StepEvent):
            # Só o nó de ferramentas tem o que mostrar; os outros passos são internos.
            if event.node == "tools":
                # As três últimas: o usuário quer saber o que está acontecendo agora, não
                # o histórico do turno inteiro.
                for label in turn.tool_labels[-3:]:
                    yield "tool", {"label": label}
            return
        if event.status == "waiting_human":
            yield "action", {"pending_action": event.pending_action}
        elif event.status == "error":
            yield "error", {"message": _humanize(event.error)}

    async def stream_turn(
        self, *, user: User, thread: AiThread, state: dict[str, Any]
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """Eventos SSE do turno (regras 2 e 3): o que o agente está consultando vai
        para a tela enquanto acontece; a resposta vai quando fica pronta."""
        turn = CopilotTurn(thread=thread)
        async for event in self._drive(user, thread, state):
            self._absorb(turn, event)
            for saida in self._eventos_do_progresso(turn, event):
                yield saida
        await self._persist_reply(thread, turn)
        if turn.reply:
            yield "message", {"content": turn.reply}
        yield "done", {
            "thread_id": str(thread.id),
            "status": thread.status,
            "pending_action": turn.pending_action,
        }

    # -------------------------------------------------------------------- interno

    def _absorb(self, turn: CopilotTurn, event: StepEvent | GraphResult) -> None:
        if isinstance(event, StepEvent):
            for call in (event.output or {}).get("scratch", {}).get("tool_calls", []) or []:
                nome = str(call.get("name") if isinstance(call, dict) else call)
                turn.tool_labels.append(TOOL_LABELS.get(nome, f"consultando {nome}"))
            return
        if event.status == "done":
            turn.reply = (event.output or {}).get("answer")
        elif event.status == "waiting_human":
            turn.pending_action = event.pending_action
            # Regra 11: o copiloto NÃO diz que fez — diz que preparou e está esperando.
            turn.reply = _pending_reply(event.pending_action)
        elif event.status == "error":
            turn.error = _humanize(event.error)
            turn.reply = turn.error

    async def _drive(
        self, user: User, thread: AiThread, state: dict[str, Any]
    ) -> AsyncIterator[StepEvent | GraphResult]:
        runtime = await self._runtime(user, thread)
        self.threads.runtime = runtime
        async for event in runtime.stream(thread, input_=state["input"]):
            yield event

    async def _runtime(self, user: User, thread: AiThread) -> GraphRuntime:
        context = dict(thread.context or {})
        tool_ctx = ToolContext(
            session=self.session,
            tenant_id=self.tenant_id,
            user=user,
            thread_id=thread.id,
            screen_context=context,
        )
        runner = AiRunner(self.session, self.tenant_id, self.provider)
        if thread.model:
            # Regra 9: a escolha do usuário vale para ESTE thread, acima da configuração
            # da feature.
            runner = AiRunner(
                self.session, self.tenant_id, self.provider, model_override=thread.model
            )
        return GraphRuntime(
            self.session,
            self.tenant_id,
            deps=GraphDeps(
                tenant_id=self.tenant_id,
                user_id=user.id,
                llm=runner,
                feature_key=COPILOT_FEATURE,
                tools={spec.name: spec for spec in tool_specs(user)},
                tool_runner=ToolRunner(tool_ctx),
                context=context,
            ),
        )

    async def _resolve_thread(
        self,
        user: User,
        thread_id: uuid.UUID | None,
        message: str,
        context: dict[str, Any] | None,
        model: str | None,
    ) -> AiThread:
        if thread_id is not None:
            thread = await self.threads.get_for(thread_id, user)
            if context:
                thread.context = context
            if model:
                thread.model = model
            thread.archived_at = None
            return thread
        if self.thread_sessions is None:
            thread = await self.threads.create(
                user=user,
                graph_name=COPILOT_GRAPH,
                title=_title_from(message),  # regra 6
                context=context or {},
            )
        else:
            # Spec 103: a conversa nova é comitada antes do turno rodar. Sem isso, um
            # timeout dentro de uma query não teria onde gravar o passo de erro — a
            # linha do thread ainda não existiria para a conexão que faz o registro.
            thread_id = await create_durable_thread(
                self.thread_sessions,
                user=user,
                tenant_id=self.tenant_id,
                graph_name=COPILOT_GRAPH,
                title=_title_from(message),  # regra 6
                context=context or {},
            )
            thread = await self.threads.get_for(thread_id, user)
        thread.model = model
        return thread

    async def _history_state(self, thread: AiThread, *, store: bool) -> list[dict[str, Any]]:
        """Sem opt-in não há texto guardado, então o histórico da conversa vive no
        estado do thread (que é efêmero por natureza) em vez de em `ai_messages`."""
        if not store:
            return list((thread.state or {}).get("messages") or [])
        return [
            {"role": message.role, "content": message.content or ""}
            for message in await self.messages.list_for_thread(thread.id)
            if message.content
        ]

    async def _persist_reply(self, thread: AiThread, turn: CopilotTurn) -> None:
        feature = await self.config.resolve(COPILOT_FEATURE)
        action_id = None
        if turn.pending_action:
            raw = turn.pending_action.get("action_id")
            action_id = uuid.UUID(str(raw)) if raw else None
        self.session.add(
            AiMessage(
                tenant_id=self.tenant_id,
                thread_id=thread.id,
                role="assistant",
                content=turn.reply if feature.store_prompts else None,
                action_id=action_id,
            )
        )
        thread.updated_at = datetime.now(UTC)
        await self.session.flush()

    # ------------------------------------------------------------------ histórico

    async def list_messages(self, thread: AiThread) -> Sequence[AiMessage]:
        return await self.messages.list_for_thread(thread.id)

    async def delete_thread(self, thread: AiThread, user: User) -> None:
        """Apagar a conversa é do dono. As ações já executadas continuam no
        `ai_audit_log` — o histórico do que a IA FEZ não se apaga com a conversa."""
        self.threads._ensure_owner(thread, user)
        await self.session.delete(thread)
        await self.session.flush()

    async def archive_inactive(self, *, now: datetime | None = None) -> int:
        """Regra 7: 30 dias sem uso arquiva (o expurgo dos 90 é do worker da 082)."""
        cutoff = (now or datetime.now(UTC)) - timedelta(days=ARCHIVE_AFTER_DAYS)
        stmt = select(AiThread).where(
            AiThread.graph_name == COPILOT_GRAPH,
            AiThread.archived_at.is_(None),
            AiThread.updated_at < cutoff,
        )
        rows = list((await self.session.scalars(stmt)).all())
        for thread in rows:
            thread.archived_at = datetime.now(UTC)
            if thread.status == ThreadStatus.WAITING_HUMAN.value:
                thread.status = ThreadStatus.CANCELLED.value
        await self.session.flush()
        return len(rows)


def _title_from(message: str) -> str:
    limpo = " ".join(message.split())
    return limpo[:TITLE_MAX_CHARS] + ("…" if len(limpo) > TITLE_MAX_CHARS else "")


def _pending_reply(pending: dict[str, Any] | None) -> str:
    """Regra 11: a frase não pode dar a entender que já aconteceu."""
    titulo = (pending or {}).get("title") or "a ação"
    return (
        f"Preparei: {titulo}. **Nada foi gravado ainda** — confira abaixo e confirme "
        "para eu executar."
    )


def _humanize(error: str | None) -> str:
    """Regra 12: erro em português, sem stack trace nem jargão."""
    if not error:
        return "Não consegui concluir agora. Tente de novo em instantes."
    if "excedeu" in error or "timeout" in error.lower():
        return "A consulta demorou demais e foi interrompida. Tente uma pergunta mais específica."
    if "passos" in error:
        return "A conversa ficou complexa demais para uma resposta só. Divida em perguntas menores."
    return "Não consegui concluir agora. Tente reformular a pergunta."


__all__ = [
    "ARCHIVE_AFTER_DAYS",
    "COPILOT_FEATURE",
    "MAX_MESSAGES_PER_THREAD",
    "TOOL_LABELS",
    "CopilotService",
    "CopilotTurn",
    "CopilotUnavailableError",
    "FeatureDisabledError",
    "LLMNotConfiguredError",
    "ThreadLimitReachedError",
]
