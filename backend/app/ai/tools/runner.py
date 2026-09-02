"""Execução de ferramenta (spec 083).

O runner é o guarda-corpo entre o modelo e o banco: valida os argumentos contra o
schema, checa o RBAC do usuário, corta o resultado no teto, registra a chamada e
**nunca deixa uma exceção escapar para o grafo** — erro de ferramenta volta como
mensagem estruturada para o modelo poder se corrigir (regra 8).
"""

import json
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ValidationError

from app.ai.tools.base import (
    MAX_CALLS_PER_STEP,
    MAX_OUTPUT_BYTES,
    ToolContext,
    ToolDef,
    ToolError,
    get_tool,
)
from app.ai.tools.write import WriteToolDef, get_write_tool
from app.domain.ai.models import AiToolCall

if TYPE_CHECKING:  # o import de execução é lazy em `_propose_write` (ciclo de módulo)
    from app.domain.ai.models import AiAction

logger = logging.getLogger("rito.ai.tools")

_SUMMARY_MAX_CHARS = 300


def _summarize(payload: dict[str, Any]) -> tuple[str, int | None]:
    """Resumo curto para o log — nunca o conteúdo lido (ver o cabeçalho da migration)."""
    items = payload.get("items")
    row_count = len(items) if isinstance(items, list) else None
    keys = ", ".join(sorted(str(key) for key in payload))
    summary = f"{row_count if row_count is not None else '—'} linha(s); campos: {keys}"
    return summary[:_SUMMARY_MAX_CHARS], row_count


def _fit_rows(payload: dict[str, Any], items: list[Any]) -> list[Any]:
    """Corta a lista pela metade até o payload caber — nunca abaixo de uma linha.

    Metade a cada volta, e não uma linha a cada volta, porque a serialização é o custo do
    laço: uma lista de 10 mil linhas levaria 10 mil serializações no caminho linear e leva
    14 aqui. A saída com uma linha só é deliberada: o modelo precisa ver a FORMA do
    resultado para saber como refinar o filtro, e forma nenhuma não ajuda ninguém.
    """
    kept = items
    while (
        kept
        and len(json.dumps({**payload, "items": kept}, ensure_ascii=False, default=str).encode())
        > MAX_OUTPUT_BYTES
    ):
        kept = kept[: max(1, len(kept) // 2)]
        if len(kept) == 1:
            break
    return kept


def cap_output(payload: dict[str, Any]) -> dict[str, Any]:
    """Regra 5: saída acima de 20 KB é resumida, com o aviso explícito.

    O corte é por LINHAS, não por bytes cegos: devolver meio JSON quebrado seria pior
    para o modelo do que devolver menos linhas e dizer que cortou.
    """
    encoded = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    if len(encoded) <= MAX_OUTPUT_BYTES:
        return payload
    items = payload.get("items")
    if isinstance(items, list) and items:
        kept = _fit_rows(payload, items)
        return {
            **payload,
            "items": kept,
            "truncated": True,
            "truncation_note": (
                f"Resultado grande demais ({len(encoded)} bytes): "
                f"{len(kept)} de {len(items)} linhas. Refine os filtros."
            ),
        }
    return {
        "truncated": True,
        "truncation_note": (
            f"Resultado grande demais ({len(encoded)} bytes) para caber na resposta. "
            "Peça um recorte menor."
        ),
        "keys": sorted(str(key) for key in payload),
    }


def _validated_params(definition: ToolDef, name: str, arguments: dict[str, Any]) -> BaseModel:
    """Argumentos do modelo validados pelo schema da ferramenta.

    O erro vira `ToolError`, não `ValidationError`: quem lê é o MODELO, na volta seguinte
    da conversa, e ele precisa de uma frase que diga o que corrigir. Só o primeiro problema
    entra na mensagem — despejar dez erros de Pydantic gasta contexto e não ajuda a acertar.
    """
    try:
        return definition.params_model.model_validate(arguments)
    except ValidationError as exc:
        raise ToolError(
            "invalid_arguments",
            f"Argumentos inválidos para {name}: {exc.error_count()} problema(s). "
            f"{exc.errors()[0].get('msg', '')}",
        ) from exc


def _pending_payload(action: "AiAction", kind: str) -> dict[str, Any]:
    """O que o modelo recebe no lugar da escrita (spec 084, regra 1).

    O `note` é para o modelo, não para a tela: sem ele o modelo lê `pending_action` e
    responde ao usuário como se tivesse gravado. Dizer «nada foi gravado» em português, no
    corpo da resposta da ferramenta, é o que impede essa alucinação.
    """
    return {
        "pending_action": {
            "action_id": str(action.id),
            "kind": kind,
            "status": action.status,
            "title": action.preview.get("summary", kind),
            "preview": action.preview,
        },
        "note": (
            "Nada foi gravado. A ação está aguardando confirmação do usuário."
            if action.status == "pending"
            else f"A ação foi recusada automaticamente: {action.rejection_reason}"
        ),
    }


class ToolRunner:
    """Um runner por PASSO do grafo — é ele que conta as chamadas do passo (regra 11)."""

    def __init__(self, ctx: ToolContext, *, max_calls: int = MAX_CALLS_PER_STEP) -> None:
        self.ctx = ctx
        self.max_calls = max_calls
        self.calls_in_step = 0

    def begin_step(self) -> None:
        self.calls_in_step = 0

    async def _failed(
        self,
        name: str,
        arguments: dict[str, Any],
        started: float,
        erro: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Registra a chamada que falhou e devolve ao modelo o payload de erro.

        O `erro` guardado e o `payload` devolvido são diferentes de propósito: a auditoria
        recebe a mensagem crua (que pode conter detalhe interno), e o modelo recebe só o
        recado que serve para ele decidir o próximo passo.
        """
        await self._record(
            name, arguments, summary=None, row_count=None, started=started, error=erro
        )
        return payload

    def _check_step_budget(self) -> None:
        """Regra 4: o passo tem um teto de consultas, e estourá-lo é `ToolError`, não crash.

        Erro de ferramenta volta para o modelo como resposta, então ele lê o recado e decide
        o que fazer — que é o único jeito de o limite não virar uma conversa interrompida no
        meio. O texto fala com o MODELO, não com o usuário.
        """
        if self.calls_in_step >= self.max_calls:
            raise ToolError(
                "too_many_calls",
                (
                    f"Limite de {self.max_calls} consultas por passo atingido. "
                    "Responda com o que já tem ou peça mais detalhes ao usuário."
                ),
            )

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        try:
            self._check_step_budget()
            write_definition = get_write_tool(name)
            if write_definition is not None:
                return await self._propose_write(write_definition, arguments, started)
            definition = get_tool(name)
            definition.check_permission(self.ctx.user)
            params = _validated_params(definition, name, arguments)
            self.calls_in_step += 1
            payload = cap_output(await definition.handler(self.ctx, params))
        except ToolError as exc:
            return await self._failed(name, arguments, started, exc.message, exc.to_payload())
        except Exception as exc:  # regra 8: nem erro inesperado derruba o grafo
            logger.exception("Ferramenta %s falhou", name)
            recado = f"A consulta {name} falhou. Tente outra abordagem."
            return await self._failed(
                name, arguments, started, str(exc), ToolError("tool_failed", recado).to_payload()
            )

        summary, row_count = _summarize(payload)
        await self._record(
            name, arguments, summary=summary, row_count=row_count, started=started, error=None
        )
        return payload

    async def _propose_write(
        self, definition: WriteToolDef, arguments: dict[str, Any], started: float
    ) -> dict[str, Any]:
        """Spec 084, regra 1: ferramenta de escrita NUNCA grava — ela cria uma proposta
        pendente e devolve ao modelo um `pending_action`, que faz o grafo interromper e
        esperar a pessoa (spec 082, regra 2)."""
        from app.domain.ai.actions import AiActionService, TooManyPendingError

        self.calls_in_step += 1
        service = AiActionService(self.ctx.session, self.ctx.tenant_id)
        try:
            action = await service.propose(ctx=self.ctx, definition=definition, arguments=arguments)
        except TooManyPendingError as exc:
            raise ToolError(
                "too_many_pending",
                (
                    "Já há confirmações pendentes demais nesta conversa. "
                    "Peça ao usuário para decidir as anteriores primeiro."
                ),
            ) from exc
        await self._record(
            definition.name,
            arguments,
            summary=f"proposta {action.status}",
            row_count=None,
            started=started,
            error=action.rejection_reason,
        )
        return _pending_payload(action, definition.name)

    async def _record(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        summary: str | None,
        row_count: int | None,
        started: float,
        error: str | None,
    ) -> None:
        self.ctx.session.add(
            AiToolCall(
                tenant_id=self.ctx.tenant_id,
                thread_id=self.ctx.thread_id,
                user_id=self.ctx.user.id,
                tool_name=name,
                arguments=_jsonable(arguments),
                result_summary=summary,
                row_count=row_count,
                duration_ms=int((time.monotonic() - started) * 1000),
                error=error[:500] if error else None,
            )
        )
        await self.ctx.session.flush()


def _jsonable(arguments: dict[str, Any]) -> dict[str, Any]:
    """Argumentos vêm do modelo como JSON, mas um chamador interno pode passar UUID."""
    return {
        key: (str(value) if isinstance(value, uuid.UUID) else value)
        for key, value in arguments.items()
    }
