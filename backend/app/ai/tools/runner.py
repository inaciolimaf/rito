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
from typing import Any

from pydantic import ValidationError

from app.ai.tools.base import (
    MAX_CALLS_PER_STEP,
    MAX_OUTPUT_BYTES,
    ToolContext,
    ToolError,
    get_tool,
)
from app.ai.tools.write import WriteToolDef, get_write_tool
from app.domain.ai.models import AiToolCall

logger = logging.getLogger("rito.ai.tools")

_SUMMARY_MAX_CHARS = 300


def _summarize(payload: dict[str, Any]) -> tuple[str, int | None]:
    """Resumo curto para o log — nunca o conteúdo lido (ver o cabeçalho da migration)."""
    items = payload.get("items")
    row_count = len(items) if isinstance(items, list) else None
    keys = ", ".join(sorted(str(key) for key in payload))
    summary = f"{row_count if row_count is not None else '—'} linha(s); campos: {keys}"
    return summary[:_SUMMARY_MAX_CHARS], row_count


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
        kept = items
        while (
            kept
            and len(
                json.dumps({**payload, "items": kept}, ensure_ascii=False, default=str).encode(
                    "utf-8"
                )
            )
            > MAX_OUTPUT_BYTES
        ):
            kept = kept[: max(1, len(kept) // 2)]
            if len(kept) == 1:
                break
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


class ToolRunner:
    """Um runner por PASSO do grafo — é ele que conta as chamadas do passo (regra 11)."""

    def __init__(self, ctx: ToolContext, *, max_calls: int = MAX_CALLS_PER_STEP) -> None:
        self.ctx = ctx
        self.max_calls = max_calls
        self.calls_in_step = 0

    def begin_step(self) -> None:
        self.calls_in_step = 0

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        try:
            if self.calls_in_step >= self.max_calls:
                raise ToolError(
                    "too_many_calls",
                    (
                        f"Limite de {self.max_calls} consultas por passo atingido. "
                        "Responda com o que já tem ou peça mais detalhes ao usuário."
                    ),
                )
            write_definition = get_write_tool(name)
            if write_definition is not None:
                return await self._propose_write(write_definition, arguments, started)
            definition = get_tool(name)
            definition.check_permission(self.ctx.user)
            try:
                params = definition.params_model.model_validate(arguments)
            except ValidationError as exc:
                raise ToolError(
                    "invalid_arguments",
                    f"Argumentos inválidos para {name}: {exc.error_count()} problema(s). "
                    f"{exc.errors()[0].get('msg', '')}",
                ) from exc
            self.calls_in_step += 1
            payload = cap_output(await definition.handler(self.ctx, params))
        except ToolError as exc:
            await self._record(
                name, arguments, summary=None, row_count=None, started=started, error=exc.message
            )
            return exc.to_payload()
        except Exception as exc:  # regra 8: nem erro inesperado derruba o grafo
            logger.exception("Ferramenta %s falhou", name)
            await self._record(
                name, arguments, summary=None, row_count=None, started=started, error=str(exc)
            )
            return ToolError(
                "tool_failed", f"A consulta {name} falhou. Tente outra abordagem."
            ).to_payload()

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
        return {
            "pending_action": {
                "action_id": str(action.id),
                "kind": definition.name,
                "status": action.status,
                "title": action.preview.get("summary", definition.name),
                "preview": action.preview,
            },
            "note": (
                "Nada foi gravado. A ação está aguardando confirmação do usuário."
                if action.status == "pending"
                else f"A ação foi recusada automaticamente: {action.rejection_reason}"
            ),
        }

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
