"""Tradução de `LLMChunk` para eventos SSE (spec 081, regra 8).

Os quatro eventos do contrato — `chunk`, `tool_call`, `done`, `error` — saem daqui já
no formato do wire, para as features da fase 8 (085+) só encanarem. O formato é o do
padrão `text/event-stream`: uma linha `event:`, uma `data:` com JSON, linha em branco.
"""

import json
from collections.abc import AsyncIterator

from app.integrations.openrouter.types import LLMChunk

SSE_MEDIA_TYPE = "text/event-stream"


def format_event(chunk: LLMChunk) -> str:
    payload: dict[str, object] = {}
    if chunk.kind == "chunk":
        payload = {"content": chunk.content or ""}
    elif chunk.kind == "tool_call" and chunk.tool_call is not None:
        payload = {
            "id": chunk.tool_call.id,
            "name": chunk.tool_call.name,
            "arguments": chunk.tool_call.arguments,
        }
    elif chunk.kind == "done":
        payload = {"finish_reason": chunk.finish_reason}
        if chunk.usage is not None:
            payload["usage"] = {
                "prompt_tokens": chunk.usage.prompt_tokens,
                "completion_tokens": chunk.usage.completion_tokens,
                "cost_usd": chunk.usage.cost_usd,
            }
    elif chunk.kind == "error":
        payload = {"message": chunk.error or "Falha na geração."}
    return f"event: {chunk.kind}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def event_stream(chunks: AsyncIterator[LLMChunk]) -> AsyncIterator[str]:
    async for chunk in chunks:
        yield format_event(chunk)
