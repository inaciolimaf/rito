"""Assistência de escrita dentro do editor (spec 088).

Cinco ajudas — continuar, reescrever, ajustar o tom, revisar e fundamentar — com uma
regra em comum: **a IA propõe texto, quem escreve continua sendo a pessoa**. Nada entra
no documento por conta própria; o que este service devolve é sugestão, e é o editor que
insere (ou não) mediante gesto.

A revisão é o caso mais explícito disso: ela devolve checklist e **não** toca no texto
(regra 6). Apontar é útil; corrigir por cima do trabalho de alguém, não.
"""

import json
import logging
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import load_prompt
from app.ai.tools.base import ToolContext
from app.ai.tools.runner import ToolRunner
from app.core.repository import BaseRepository
from app.domain.ai.models import EditorAiAction
from app.domain.ai.service import AiRunner
from app.domain.legal_agents.citations import strip_unsupported_citations
from app.domain.templates.repository import TemplateRepository
from app.domain.users.models import User
from app.integrations.openrouter.types import LLMChunk, Message

logger = logging.getLogger("rito.ai.editor")

FEATURE_KEY = "editor_assist"

# Regra 8: o contexto enviado é recortado — prompt maior é conta maior, e o modelo não
# escreve melhor com o documento inteiro do que com o parágrafo certo.
CONTEXT_BEFORE_LIMIT = 2000
CONTEXT_AFTER_LIMIT = 500
# Regra 9.
MAX_SELECTION = 5000

Tone = Literal["formal", "objetivo", "tecnico", "simples"]

# Regra 4.
TONE_INSTRUCTIONS: dict[str, str] = {
    "formal": "Reescreva em registro formal forense, sem rebuscamento gratuito.",
    "objetivo": "Reescreva de forma objetiva: frases curtas, sem adjetivação supérflua.",
    "tecnico": "Reescreva com precisão técnica, usando a terminologia jurídica correta.",
    "simples": "Reescreva em linguagem simples, compreensível por quem não é advogado, "
    "sem perder o sentido jurídico.",
}

# Regra 5: os cinco eixos da revisão. A lista é fixa para que duas revisões da mesma
# peça sejam comparáveis.
REVIEW_TOPICS: tuple[tuple[str, str], ...] = (
    ("estrutura", "Estrutura da peça"),
    ("fundamentacao", "Fundamentação"),
    ("pedidos", "Pedidos"),
    ("coerencia", "Coerência de datas e valores"),
    ("linguagem", "Linguagem"),
)

_BASE_SYSTEM = load_prompt("editor_assist")

_REVIEW_SYSTEM = load_prompt("editor_review")

_GROUND_SYSTEM = load_prompt("editor_ground")


class SelectionTooLongError(Exception):
    """Regra 9: seleção acima de 5.000 caracteres → 422 pedindo para reduzir."""


class ActionNotFoundError(Exception):
    """Feedback para ação inexistente → 404."""


@dataclass(frozen=True)
class ReviewItem:
    topic: str
    label: str
    status: str
    note: str


@dataclass
class EditorResult:
    action: EditorAiAction
    output: str
    # Regra 7: citações removidas por não constarem no processo.
    warnings: list[dict[str, str]]


class EditorAiRepository(BaseRepository[EditorAiAction]):
    model = EditorAiAction

    async def list_for_template(self, template_id: uuid.UUID) -> Sequence[EditorAiAction]:
        stmt = (
            select(EditorAiAction)
            .where(EditorAiAction.template_id == template_id)
            .order_by(EditorAiAction.created_at.desc())
        )
        return (await self.session.scalars(stmt)).all()


def clip_context(before: str, after: str = "") -> tuple[str, str]:
    """Regra 8: o que vai para o modelo é o fim do texto anterior e o começo do
    seguinte — é onde o cursor está, e é o que importa para continuar a frase."""
    return before[-CONTEXT_BEFORE_LIMIT:], after[:CONTEXT_AFTER_LIMIT]


def parse_review(raw: str | None) -> list[ReviewItem]:
    """Checklist estruturado, com os cinco tópicos sempre presentes (regra 5).

    Tópico que o modelo esqueceu vira "não avaliado" em vez de sumir: uma revisão com
    quatro itens parece completa e não é.
    """
    payload: dict[str, Any] = {}
    texto = (raw or "").strip()
    inicio, fim = texto.find("{"), texto.rfind("}")
    if inicio >= 0 and fim > inicio:
        try:
            candidato = json.loads(texto[inicio : fim + 1])
            payload = candidato if isinstance(candidato, dict) else {}
        except json.JSONDecodeError:
            logger.warning("Revisão do editor veio em formato ilegível.")
    por_topico = {
        str(item.get("topic")): item
        for item in payload.get("items") or []
        if isinstance(item, dict)
    }
    itens: list[ReviewItem] = []
    for topic, label in REVIEW_TOPICS:
        bruto = por_topico.get(topic, {})
        status = str(bruto.get("status") or "nao_avaliado")
        itens.append(
            ReviewItem(
                topic=topic,
                label=label,
                status=status if status in ("ok", "atencao", "problema") else "nao_avaliado",
                note=str(bruto.get("note") or "O modelo não avaliou este ponto."),
            )
        )
    return itens


class EditorAiService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID, runner: AiRunner) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.runner = runner
        self.actions = EditorAiRepository(session)
        self.templates = TemplateRepository(session)

    # ------------------------------------------------------------------ streaming

    def continue_text(
        self,
        *,
        user: User,
        template_id: uuid.UUID | None,
        context_before: str,
        context_after: str = "",
    ) -> AsyncIterator[LLMChunk]:
        """Regra 2: o texto chega como fantasma e só entra com Tab — por isso vem em
        streaming, para a pessoa ver a frase se formar e decidir antes do fim."""
        antes, depois = clip_context(context_before, context_after)
        prompt = (
            f"Continue o texto a seguir, de onde ele parou. Escreva um ou dois "
            f"parágrafos no máximo.\n\nTEXTO ATÉ O CURSOR:\n{antes}"
        )
        if depois:
            prompt += f"\n\nO QUE VEM DEPOIS (não repita):\n{depois}"
        return self._stream_action(
            user=user,
            template_id=template_id,
            action="continue",
            instruction=None,
            input_excerpt=antes,
            prompt=prompt,
        )

    def rewrite(
        self,
        *,
        user: User,
        template_id: uuid.UUID | None,
        selection: str,
        instruction: str,
    ) -> AsyncIterator[LLMChunk]:
        """Regra 3: a saída substitui só a seleção — por isso o prompt proíbe devolver
        o texto em volta."""
        self._ensure_selection(selection)
        prompt = (
            f"Reescreva APENAS o trecho abaixo seguindo a instrução. Devolva só o trecho "
            f"reescrito, sem repetir o texto em volta.\n\nINSTRUÇÃO: {instruction}\n\n"
            f"TRECHO:\n{selection}"
        )
        return self._stream_action(
            user=user,
            template_id=template_id,
            action="rewrite",
            instruction=instruction,
            input_excerpt=selection,
            prompt=prompt,
        )

    def tone(
        self, *, user: User, template_id: uuid.UUID | None, selection: str, tone: str
    ) -> AsyncIterator[LLMChunk]:
        """Regra 4."""
        self._ensure_selection(selection)
        instrucao = TONE_INSTRUCTIONS[tone]
        prompt = (
            f"{instrucao} Devolva só o trecho reescrito, sem repetir o texto em volta.\n\n"
            f"TRECHO:\n{selection}"
        )
        return self._stream_action(
            user=user,
            template_id=template_id,
            action="tone",
            instruction=tone,
            input_excerpt=selection,
            prompt=prompt,
        )

    async def _stream_action(
        self,
        *,
        user: User,
        template_id: uuid.UUID | None,
        action: str,
        instruction: str | None,
        input_excerpt: str,
        prompt: str,
    ) -> AsyncIterator[LLMChunk]:
        """Emite os pedaços e, no fim, grava o que foi gerado — o registro precisa do
        texto inteiro, que só existe quando o stream acaba."""
        partes: list[str] = []
        async for chunk in self.runner.stream(
            feature_key=FEATURE_KEY,
            messages=[
                Message(role="system", content=_BASE_SYSTEM),
                Message(role="user", content=prompt),
            ],
            user_id=user.id,
        ):
            if chunk.kind == "chunk" and chunk.content:
                partes.append(chunk.content)
            if chunk.kind == "done":
                # O `done` do provider é engolido: quem encerra é o nosso, logo abaixo,
                # que carrega o id da ação. Dois eventos terminais confundiriam o
                # cliente — e o primeiro não teria o id.
                continue
            yield chunk
        registro = await self._record(
            user=user,
            template_id=template_id,
            action=action,
            instruction=instruction,
            input_excerpt=input_excerpt,
            output="".join(partes),
        )
        # O id vai no evento final: é com ele que o editor manda o feedback (regra 10).
        yield LLMChunk(kind="done", finish_reason=str(registro.id))

    # ------------------------------------------------------------------- síncronas

    async def review(
        self, *, user: User, template_id: uuid.UUID, lawsuit_id: uuid.UUID | None
    ) -> tuple[EditorAiAction, list[ReviewItem]]:
        """Regra 5 e 6: devolve checklist e **não** encosta no documento."""
        template = await self.templates.get_by_id(template_id)
        if template is None:
            raise ActionNotFoundError
        contexto = await self._lawsuit_context(user, lawsuit_id)
        prompt = f"PEÇA A REVISAR:\n{template.content}"
        if contexto:
            prompt += f"\n\nCONTEXTO DO PROCESSO (para conferir datas e valores):\n{contexto}"
        response = await self.runner.run(
            feature_key=FEATURE_KEY,
            messages=[
                Message(role="system", content=_REVIEW_SYSTEM),
                Message(role="user", content=prompt),
            ],
            user_id=user.id,
        )
        itens = parse_review(response.content)
        registro = await self._record(
            user=user,
            template_id=template_id,
            action="review",
            instruction=None,
            input_excerpt=template.content[:CONTEXT_BEFORE_LIMIT],
            output=json.dumps([item.__dict__ for item in itens], ensure_ascii=False),
            model=response.model,
            tokens=response.usage.prompt_tokens + response.usage.completion_tokens,
        )
        return registro, itens

    async def ground(
        self,
        *,
        user: User,
        template_id: uuid.UUID | None,
        selection: str,
        lawsuit_id: uuid.UUID,
    ) -> EditorResult:
        """Regra 7: fundamentação com o contexto REAL do processo — e o mesmo
        guarda-corpo de citação da 087, porque a tentação de inventar súmula é a
        mesma."""
        self._ensure_selection(selection)
        contexto = await self._lawsuit_context(user, lawsuit_id)
        response = await self.runner.run(
            feature_key=FEATURE_KEY,
            messages=[
                Message(role="system", content=_GROUND_SYSTEM),
                Message(
                    role="user",
                    content=(
                        f"CONTEXTO DO PROCESSO:\n{contexto}\n\nTRECHO A FUNDAMENTAR:\n{selection}"
                    ),
                ),
            ],
            user_id=user.id,
        )
        texto, removidas = strip_unsupported_citations(response.content or "", contexto)
        registro = await self._record(
            user=user,
            template_id=template_id,
            action="ground",
            instruction=None,
            input_excerpt=selection,
            output=texto,
            model=response.model,
            tokens=response.usage.prompt_tokens + response.usage.completion_tokens,
        )
        return EditorResult(action=registro, output=texto, warnings=removidas)

    async def feedback(self, action_id: uuid.UUID, *, accepted: bool) -> EditorAiAction:
        """Regra 10: aceitar ou descartar é a métrica de qualidade da feature."""
        action = await self.actions.get_by_id(action_id)
        if action is None:
            raise ActionNotFoundError
        action.accepted = accepted
        await self.session.flush()
        return action

    # -------------------------------------------------------------------- interno

    def _ensure_selection(self, selection: str) -> None:
        if len(selection) > MAX_SELECTION:
            raise SelectionTooLongError

    async def _lawsuit_context(self, user: User, lawsuit_id: uuid.UUID | None) -> str:
        """Contexto por tool calling (regra 7), com o RLS de quem pediu — sem RAG."""
        if lawsuit_id is None:
            return ""
        runner = ToolRunner(ToolContext(session=self.session, tenant_id=self.tenant_id, user=user))
        resultado = await runner.call("get_lawsuit", {"lawsuit_id": str(lawsuit_id)})
        return json.dumps(resultado, ensure_ascii=False)

    async def _record(
        self,
        *,
        user: User,
        template_id: uuid.UUID | None,
        action: str,
        instruction: str | None,
        input_excerpt: str,
        output: str,
        model: str | None = None,
        tokens: int | None = None,
    ) -> EditorAiAction:
        registro = EditorAiAction(
            tenant_id=self.tenant_id,
            template_id=template_id,
            user_id=user.id,
            action=action,
            instruction=instruction,
            input_excerpt=input_excerpt,
            output=output,
            model=model or "streaming",
            tokens_used=tokens,
        )
        self.session.add(registro)
        await self.session.flush()
        return registro
