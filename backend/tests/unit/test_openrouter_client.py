"""Camada LLM: montagem da requisição e leitura da resposta (spec 081).

Sem rede e sem fixture: estas são as funções puras do client — o formato do payload e
a tradução do que o OpenRouter devolve. É onde um erro de protocolo aparece primeiro.
"""

import json

from app.domain.ai.sse import format_event
from app.integrations.openrouter.client import (
    build_payload,
    parse_models,
    parse_response,
    parse_stream_line,
)
from app.integrations.openrouter.types import LLMChunk, Message, ToolSpec, Usage

_TOOL = ToolSpec(
    name="buscar_processo",
    description="Busca um processo pelo número.",
    parameters={"type": "object", "properties": {"numero": {"type": "string"}}},
)


def test_monta_requisicao_no_formato_do_openrouter() -> None:
    payload = build_payload(
        messages=[
            Message(role="system", content="Você é o Rito."),
            Message(role="user", content="Resuma o processo."),
        ],
        model="fabricante-x/modelo-y",
        tools=[_TOOL],
        temperature=0.4,
        max_tokens=512,
    )

    assert payload["model"] == "fabricante-x/modelo-y"
    assert payload["temperature"] == 0.4
    assert payload["max_tokens"] == 512
    # Regra 7: pedimos o custo real junto da resposta.
    assert payload["usage"] == {"include": True}
    assert payload["messages"][0] == {"role": "system", "content": "Você é o Rito."}
    assert payload["tools"][0]["function"]["name"] == "buscar_processo"
    # Sem `stream` a chave nem aparece — o OpenRouter trata ausência e false igual, mas
    # o payload é o contrato com a fixture gravada (o hash muda se mudar).
    assert "stream" not in payload


def test_parseia_resposta_com_e_sem_tool_calls() -> None:
    texto = parse_response(
        {
            "model": "fabricante-x/modelo-y",
            "choices": [
                {
                    "message": {"content": "Resumo pronto.", "role": "assistant"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 120, "completion_tokens": 30, "cost_usd": None},
        }
    )
    assert texto.content == "Resumo pronto."
    assert texto.tool_calls == []
    assert texto.usage.prompt_tokens == 120
    assert texto.finish_reason == "stop"

    com_tool = parse_response(
        {
            "model": "fabricante-x/modelo-y",
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "function": {
                                    "name": "buscar_processo",
                                    "arguments": json.dumps({"numero": "0000001-11"}),
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.00042},
        }
    )
    assert com_tool.content is None
    assert com_tool.tool_calls[0].name == "buscar_processo"
    assert com_tool.tool_calls[0].arguments == {"numero": "0000001-11"}
    # Regra 7: custo informado pelo gateway chega inteiro.
    assert com_tool.usage.cost_usd == 0.00042


def test_argumento_de_tool_ilegivel_nao_derruba_a_resposta() -> None:
    resposta = parse_response(
        {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {"id": "c1", "function": {"name": "x", "arguments": "{isso não é json"}}
                        ]
                    }
                }
            ]
        }
    )
    assert resposta.tool_calls[0].arguments == {}


def test_streaming_emite_os_quatro_tipos_de_evento() -> None:
    """Regra 8: chunk, tool_call, done e error — e nada para linha de keep-alive."""
    chunk = parse_stream_line('data: {"choices":[{"delta":{"content":"Bom "}}]}')
    tool = parse_stream_line(
        'data: {"choices":[{"delta":{"tool_calls":[{"id":"c1","function":'
        '{"name":"buscar_processo","arguments":"{}"}}]}}]}'
    )
    done = parse_stream_line('data: {"choices":[{"delta":{},"finish_reason":"stop"}]}')
    erro = parse_stream_line('data: {"error":{"message":"limite excedido"}}')
    encerramento = parse_stream_line("data: [DONE]")

    assert chunk == LLMChunk(kind="chunk", content="Bom ")
    assert tool is not None and tool.kind == "tool_call"
    assert tool.tool_call is not None and tool.tool_call.name == "buscar_processo"
    assert done is not None and done.kind == "done" and done.finish_reason == "stop"
    assert erro == LLMChunk(kind="error", error="limite excedido")
    assert encerramento == LLMChunk(kind="done")

    assert parse_stream_line(": keep-alive") is None
    assert parse_stream_line("") is None
    assert parse_stream_line('data: {"choices":[{"delta":{}}]}') is None


def test_evento_sse_sai_no_formato_do_wire() -> None:
    assert format_event(LLMChunk(kind="chunk", content="oi")) == (
        'event: chunk\ndata: {"content": "oi"}\n\n'
    )
    assert format_event(LLMChunk(kind="error", error="falhou")).startswith("event: error\n")


def test_catalogo_traz_preco_por_token_e_calcula_custo() -> None:
    modelos = parse_models(
        {
            "data": [
                {
                    "id": "fabricante-x/modelo-y",
                    "name": "Modelo Y",
                    "context_length": 128000,
                    "pricing": {"prompt": "0.0000015", "completion": "0.000006"},
                }
            ]
        }
    )

    assert modelos[0].context_length == 128000
    # Regra 7: 1.000 tokens de entrada e 500 de saída pelo preço do catálogo.
    custo = modelos[0].cost_for(Usage(prompt_tokens=1000, completion_tokens=500))
    assert round(custo, 6) == round(1000 * 0.0000015 + 500 * 0.000006, 6)


async def test_provider_le_catalogo_e_completion_de_fixture_gravada() -> None:
    """Regra 12: o caminho completo do client — payload, transporte e parse — exercitado
    contra fixture em disco. Nenhum byte sai da máquina."""
    import asyncio
    from pathlib import Path

    from app.integrations.http.client import ResilientHttpClient
    from app.integrations.http.fixtures import FixtureTransport
    from app.integrations.openrouter.client import OpenRouterProvider

    # Spec 108: `.resolve()` toca o disco. Vai para uma thread como o resto do projeto
    # (`asyncio.to_thread`), e continua devolvendo `pathlib.Path` — `FixtureTransport`
    # espera a API síncrona.
    root = (await asyncio.to_thread(Path(__file__).resolve)).parents[1] / "fixtures" / "llm"
    http = ResilientHttpClient(transport=FixtureTransport(root))
    provider = OpenRouterProvider(
        http=http, api_key="chave-de-teste", base_url="https://openrouter.ai/api/v1"
    )

    modelos = await provider.models()
    assert [modelo.id for modelo in modelos] == ["fabricante-x/modelo-y", "fabricante-z/modelo-w"]

    resposta = await provider.complete(
        messages=[Message(role="user", content="Resuma esta intimação em uma frase.")],
        model="fabricante-x/modelo-y",
    )
    assert resposta.content == "Prazo de 15 dias para contestar."
    assert resposta.usage.prompt_tokens == 42
    assert resposta.usage.cost_usd == 0.000135


async def test_sem_chave_o_provider_nao_tenta_chamar() -> None:
    """Regra 11: a ausência de chave é detectada antes de qualquer requisição."""
    import pytest

    from app.integrations.http.client import ResilientHttpClient
    from app.integrations.openrouter.client import OpenRouterProvider
    from app.integrations.openrouter.types import LLMNotConfiguredError

    provider = OpenRouterProvider(
        http=ResilientHttpClient(), api_key=None, base_url="https://openrouter.ai/api/v1"
    )

    assert provider.is_configured is False
    with pytest.raises(LLMNotConfiguredError):
        await provider.models()


async def test_stream_traduz_as_linhas_e_para_no_done() -> None:
    """Regra 8: o consumidor recebe eventos tipados, não linhas de SSE — e o iterador
    encerra no `done` (nada depois dele importa)."""
    from collections.abc import AsyncIterator

    from app.integrations.http.client import ResilientHttpClient
    from app.integrations.openrouter.client import OpenRouterProvider

    class FakeStream:
        def __init__(self, linhas: list[str]) -> None:
            self.linhas = linhas
            self.chamadas: list[dict[str, object]] = []

        async def stream_lines(
            self,
            method: str,
            url: str,
            *,
            headers: dict[str, str] | None = None,
            content: bytes | None = None,
            timeout_s: float | None = None,
        ) -> AsyncIterator[str]:
            self.chamadas.append({"url": url, "timeout_s": timeout_s, "content": content})
            for linha in self.linhas:
                yield linha

    stream = FakeStream(
        [
            ": keep-alive",
            'data: {"choices":[{"delta":{"content":"Prazo "}}]}',
            'data: {"choices":[{"delta":{"content":"de 15 dias."}}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}],'
            '"usage":{"prompt_tokens":10,"completion_tokens":4}}',
            'data: {"choices":[{"delta":{"content":"nunca chega"}}]}',
        ]
    )
    provider = OpenRouterProvider(
        http=ResilientHttpClient(),
        streaming_http=stream,
        api_key="chave-de-teste",
        base_url="https://openrouter.ai/api/v1",
    )

    eventos = [
        chunk
        async for chunk in provider.stream(
            messages=[Message(role="user", content="Resuma.")], model="fabricante-x/modelo-y"
        )
    ]

    assert [chunk.kind for chunk in eventos] == ["chunk", "chunk", "done"]
    assert "".join(chunk.content or "" for chunk in eventos) == "Prazo de 15 dias."
    assert eventos[-1].usage is not None and eventos[-1].usage.prompt_tokens == 10
    # Regra 9: streaming tem o teto próprio, de 300 s.
    assert stream.chamadas[0]["timeout_s"] == 300.0
    corpo = stream.chamadas[0]["content"]
    assert isinstance(corpo, bytes) and b'"stream": true' in corpo
