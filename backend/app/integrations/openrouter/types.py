"""Contratos da camada LLM (spec 081 §5).

`LLMProvider` é a interface que o resto do sistema conhece. OpenRouter é a única
implementação hoje (regra 1) e nenhum consumidor sabe disso: services dependem deste
Protocol e recebem a implementação por injeção (DIP, CLAUDE.md §5) — nos testes, um
fake que implemente o mesmo Protocol é intercambiável com o real (LSP).
"""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class Message:
    role: Role
    content: str
    # Preenchidos só nas mensagens de resultado de ferramenta (papel "tool").
    tool_call_id: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class ToolSpec:
    """Ferramenta oferecida ao modelo. `parameters` é JSON Schema — o formato que a
    API de tool calling espera; tipar mais que isso engessaria as tools da 083/084."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    # Custo informado pelo próprio OpenRouter; ausente, quem chama calcula pelo
    # catálogo (regra 7).
    cost_usd: float | None = None


@dataclass(frozen=True)
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    finish_reason: str = ""


@dataclass(frozen=True)
class LLMChunk:
    """Um evento do streaming (regra 8). `kind` vira o nome do evento SSE."""

    kind: Literal["chunk", "tool_call", "done", "error"]
    content: str | None = None
    tool_call: ToolCall | None = None
    finish_reason: str | None = None
    usage: Usage | None = None
    error: str | None = None


@dataclass(frozen=True)
class ModelInfo:
    """Entrada do catálogo do OpenRouter (regra 7 — o preço vem daqui)."""

    id: str
    name: str
    context_length: int
    prompt_price_usd: float
    completion_price_usd: float

    def cost_for(self, usage: Usage) -> float:
        """Preço do catálogo é POR TOKEN (não por mil) na API do OpenRouter."""
        return (
            usage.prompt_tokens * self.prompt_price_usd
            + usage.completion_tokens * self.completion_price_usd
        )


class LLMError(Exception):
    """Falha do gateway depois de esgotadas as tentativas da camada 041."""


class LLMNotConfiguredError(LLMError):
    """Sem `OPENROUTER_API_KEY` (regra 11) — a feature aparece desabilitada, o sistema
    segue de pé."""


class LLMProvider(Protocol):
    async def complete(
        self,
        *,
        messages: Sequence[Message],
        model: str,
        tools: Sequence[ToolSpec] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse: ...

    def stream(
        self,
        *,
        messages: Sequence[Message],
        model: str,
        tools: Sequence[ToolSpec] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[LLMChunk]: ...

    async def models(self) -> list[ModelInfo]: ...
