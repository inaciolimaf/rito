"""Client do OpenRouter (spec 081) — o ÚNICO caminho de saída para LLM (regra 1).

Nenhum SDK de provider é importado aqui nem em lugar nenhum de `app/` (há teste meta
que reprova). A resiliência (timeout, retry, breaker, auditoria) vem da camada 041:
este módulo só monta o payload, manda pelo `HttpClient` injetado e traduz a resposta.

Nenhum id de modelo aparece neste arquivo — modelo é sempre argumento, resolvido em
`app/domain/ai/service.py` a partir de `ai_feature_config` (regra 2).
"""

import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

from app.integrations.http.types import (
    HttpClient,
    HttpClientError,
    HttpResponse,
    StreamingHttpClient,
)
from app.integrations.openrouter.types import (
    LLMChunk,
    LLMError,
    LLMNotConfiguredError,
    LLMResponse,
    Message,
    ModelInfo,
    ToolCall,
    ToolSpec,
    Usage,
)

# Regra 9: teto por tipo de chamada.
COMPLETION_TIMEOUT_S = 120.0
STREAM_TIMEOUT_S = 300.0

# Regra 10: o OpenRouter usa estes dois headers para atribuir o tráfego. Vêm de
# configuração (OPENROUTER_SITE_URL/OPENROUTER_APP_NAME) — quem hospeda o Rito não é
# necessariamente rito.app.


def build_payload(
    *,
    messages: Sequence[Message],
    model: str,
    tools: Sequence[ToolSpec] | None,
    temperature: float,
    max_tokens: int | None,
    stream: bool = False,
) -> dict[str, Any]:
    """Payload no formato de chat completions do OpenRouter.

    `usage.include` pede o custo real na resposta (regra 7) — sem isso, o consumidor
    teria que calcular pelo catálogo sempre.
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": [_message_to_dict(message) for message in messages],
        "temperature": temperature,
        "usage": {"include": True},
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if tools:
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]
    if stream:
        payload["stream"] = True
    return payload


def _message_to_dict(message: Message) -> dict[str, Any]:
    payload: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_call_id is not None:
        payload["tool_call_id"] = message.tool_call_id
    if message.name is not None:
        payload["name"] = message.name
    return payload


def _parse_tool_calls(raw_calls: list[dict[str, Any]] | None) -> list[ToolCall]:
    """Argumentos vêm como STRING JSON no protocolo; argumento ilegível não derruba a
    resposta inteira — vira dicionário vazio e quem executa a tool valida (084)."""
    calls: list[ToolCall] = []
    for raw in raw_calls or []:
        function = raw.get("function") or {}
        try:
            arguments = json.loads(function.get("arguments") or "{}")
        except json.JSONDecodeError:
            arguments = {}
        calls.append(
            ToolCall(
                id=str(raw.get("id") or ""),
                name=str(function.get("name") or ""),
                arguments=arguments if isinstance(arguments, dict) else {},
            )
        )
    return calls


def _parse_usage(raw: dict[str, Any] | None) -> Usage:
    raw = raw or {}
    cost = raw.get("cost")
    return Usage(
        prompt_tokens=int(raw.get("prompt_tokens") or 0),
        completion_tokens=int(raw.get("completion_tokens") or 0),
        cost_usd=float(cost) if cost is not None else None,
    )


def parse_response(body: dict[str, Any]) -> LLMResponse:
    """Resposta com ou sem tool calls (o modelo escolhe uma das duas formas)."""
    choices = body.get("choices") or []
    choice = choices[0] if choices else {}
    message = choice.get("message") or {}
    return LLMResponse(
        content=message.get("content"),
        tool_calls=_parse_tool_calls(message.get("tool_calls")),
        usage=_parse_usage(body.get("usage")),
        model=str(body.get("model") or ""),
        finish_reason=str(choice.get("finish_reason") or ""),
    )


def parse_stream_line(line: str) -> LLMChunk | None:
    """Uma linha de SSE do OpenRouter → um evento nosso (regra 8).

    Linha vazia, comentário (`: keep-alive`) e delta sem conteúdo devolvem `None` —
    quem consome ignora, em vez de mandar chunk vazio para a UI.
    """
    line = line.strip()
    if not line or line.startswith(":") or not line.startswith("data:"):
        return None
    data = line[len("data:") :].strip()
    if data == "[DONE]":
        return LLMChunk(kind="done")
    try:
        body = json.loads(data)
    except json.JSONDecodeError:
        return LLMChunk(kind="error", error="Resposta de streaming ilegível.")
    return _chunk_do_corpo(body)


def _chunk_do_corpo(body: dict[str, Any]) -> LLMChunk | None:
    """O CONTEÚDO de um evento de streaming, já desembrulhado do envelope SSE.

    A separação é a da spec 106: acima mora o protocolo (linha vazia, comentário, prefixo
    `data:`, `[DONE]`, JSON ilegível); aqui mora o que o modelo disse. As duas coisas
    mudam por motivos diferentes — o envelope é do SSE, o corpo é do OpenRouter.
    """
    if body.get("error"):
        error = body["error"]
        message = error.get("message") if isinstance(error, dict) else error
        return LLMChunk(kind="error", error=str(message))
    choices = body.get("choices") or []
    choice = choices[0] if choices else {}
    delta = choice.get("delta") or {}
    tool_calls = _parse_tool_calls(delta.get("tool_calls"))
    if tool_calls:
        return LLMChunk(kind="tool_call", tool_call=tool_calls[0])
    if choice.get("finish_reason"):
        return LLMChunk(
            kind="done",
            finish_reason=str(choice["finish_reason"]),
            usage=_parse_usage(body["usage"]) if body.get("usage") else None,
        )
    content = delta.get("content")
    return LLMChunk(kind="chunk", content=str(content)) if content else None


def parse_models(body: dict[str, Any]) -> list[ModelInfo]:
    """Catálogo do OpenRouter. Preço vem como string por token (não por mil)."""
    models: list[ModelInfo] = []
    for raw in body.get("data") or []:
        pricing = raw.get("pricing") or {}
        models.append(
            ModelInfo(
                id=str(raw.get("id") or ""),
                name=str(raw.get("name") or raw.get("id") or ""),
                context_length=int(raw.get("context_length") or 0),
                prompt_price_usd=float(pricing.get("prompt") or 0.0),
                completion_price_usd=float(pricing.get("completion") or 0.0),
            )
        )
    return models


class OpenRouterProvider:
    """Implementação de `LLMProvider` (spec 081 §5)."""

    def __init__(
        self,
        *,
        http: HttpClient,
        api_key: str | None,
        base_url: str,
        streaming_http: StreamingHttpClient | None = None,
        site_url: str = "https://rito.app",
        app_name: str = "Rito",
    ) -> None:
        self._http = http
        self._streaming_http = streaming_http
        self._api_key = (api_key or "").strip()
        self._base_url = base_url.rstrip("/")
        self._site_url = site_url
        self._app_name = app_name

    @property
    def is_configured(self) -> bool:
        """Regra 11: sem chave, quem chama desabilita a feature — não quebra."""
        return bool(self._api_key)

    def _headers(self) -> dict[str, str]:
        if not self.is_configured:
            raise LLMNotConfiguredError(
                "OPENROUTER_API_KEY não configurada — as features de IA ficam desabilitadas."
            )
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self._site_url,  # regra 10
            "X-Title": self._app_name,
        }

    async def complete(
        self,
        *,
        messages: Sequence[Message],
        model: str,
        tools: Sequence[ToolSpec] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        payload = build_payload(
            messages=messages,
            model=model,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        response = await self._post("/chat/completions", payload)
        if response.status_code >= 400:
            raise LLMError(f"OpenRouter respondeu {response.status_code}: {response.text[:200]}")
        return parse_response(response.json())

    async def stream(
        self,
        *,
        messages: Sequence[Message],
        model: str,
        tools: Sequence[ToolSpec] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[LLMChunk]:
        """Streaming de verdade: traduz cada linha conforme chega (regra 8). Erro no
        meio do stream vira evento `error` — a UI já recebeu parte do texto e precisa
        saber que o resto não vem."""
        if self._streaming_http is None:
            raise LLMError("Provider montado sem transporte de streaming.")
        payload = build_payload(
            messages=messages,
            model=model,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        try:
            async for line in self._streaming_http.stream_lines(
                "POST",
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
                content=json.dumps(payload).encode(),
                timeout_s=STREAM_TIMEOUT_S,
            ):
                chunk = parse_stream_line(line)
                if chunk is None:
                    continue
                yield chunk
                if chunk.kind in ("done", "error"):
                    return
        except HttpClientError as exc:
            yield LLMChunk(kind="error", error=str(exc))
            return
        # Stream que fechou sem `[DONE]` ainda precisa terminar para quem consome.
        yield LLMChunk(kind="done", finish_reason="stop")

    async def models(self) -> list[ModelInfo]:
        response = await self._http.request(
            "GET", f"{self._base_url}/models", headers=self._headers()
        )
        if response.status_code >= 400:
            raise LLMError(f"OpenRouter respondeu {response.status_code} no catálogo de modelos.")
        return parse_models(response.json())

    async def _post(self, path: str, payload: dict[str, Any]) -> HttpResponse:
        try:
            return await self._http.request(
                "POST",
                f"{self._base_url}{path}",
                headers=self._headers(),
                content=json.dumps(payload).encode(),
            )
        except HttpClientError as exc:
            raise LLMError(str(exc)) from exc
