"""Grafo base reutilizável (spec 082 §2).

É o esqueleto que os agentes das specs 085+ herdam: um roteador de entrada que sabe
onde continuar (o que torna o grafo retomável), um nó que conversa com o modelo pela
camada 081 e uma saída. Ferramentas entram nas specs 083/084 — o nó `tools` já existe
e devolve o controle ao modelo, mas o registro de ferramentas chega vazio por enquanto.

Este é o único módulo que importa LangGraph no caminho de execução; ele é carregado
sob demanda (`app/ai/graphs/__init__.py` não importa nada).
"""

import json
from typing import Any

from langgraph.graph import END, StateGraph

from app.ai.graphs.base import (
    PENDING_ACTION_KEY,
    GraphDeps,
    GraphState,
    register_graph_placeholder,
)
from app.integrations.openrouter.types import Message

SYSTEM_PROMPT = (
    "Você é o assistente do Rito, um sistema de gestão para escritórios de advocacia "
    "brasileiros. Responda em português do Brasil, de forma objetiva. Você não tem "
    "acesso a nenhum dado do escritório além do que receber nesta conversa."
)


def _messages_for(state: GraphState) -> list[Message]:
    history = [Message(role="system", content=SYSTEM_PROMPT)]
    for raw in state.get("messages") or []:
        history.append(Message(role=raw.get("role", "user"), content=raw.get("content", "")))
    pergunta = (state.get("input") or {}).get("question")
    if pergunta:
        history.append(Message(role="user", content=str(pergunta)))
    return history


class BaseAgentGraph:
    """Roteador → modelo → fim, com o nó de ferramentas já no lugar."""

    name = "base_agent"
    feature_key = "copilot"

    def build(self, deps: GraphDeps) -> Any:
        graph = StateGraph(GraphState)

        async def think(state: GraphState) -> dict[str, Any]:
            """Uma volta de conversa com o modelo. O `llm` é o `AiRunner` da 081: o
            modelo efetivo, o fallback e a contabilidade já vêm resolvidos de lá."""
            response = await deps.llm.run(
                feature_key=deps.feature_key,
                messages=_messages_for(state),
                user_id=deps.user_id,
                tools=list(deps.tools.values()) or None,
            )
            messages = [*(state.get("messages") or [])]
            if response.content:
                messages.append({"role": "assistant", "content": response.content})
            if response.tool_calls:
                return {
                    "messages": messages,
                    "scratch": {
                        **(state.get("scratch") or {}),
                        "tool_calls": [
                            {"id": call.id, "name": call.name, "arguments": call.arguments}
                            for call in response.tool_calls
                        ],
                    },
                }
            return {"messages": messages, "output": {"answer": response.content}}

        async def use_tools(state: GraphState) -> dict[str, Any]:
            """Executa o que o modelo pediu e devolve o resultado como mensagem de
            ferramenta (spec 083). Erro de ferramenta também volta como mensagem: o
            agente precisa poder se corrigir, não estourar."""
            pedidas = (state.get("scratch") or {}).get("tool_calls") or []
            if deps.tool_runner is None:
                return {
                    "scratch": {**(state.get("scratch") or {}), "tool_calls": []},
                    "output": {"answer": None, "unavailable_tools": [c["name"] for c in pedidas]},
                }
            deps.tool_runner.begin_step()
            messages = [*(state.get("messages") or [])]
            for call in pedidas:
                result = await deps.tool_runner.call(call["name"], call.get("arguments") or {})
                messages.append(
                    {
                        "role": "tool",
                        "name": call["name"],
                        "tool_call_id": call.get("id", ""),
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )
            return {
                "messages": messages,
                "scratch": {**(state.get("scratch") or {}), "tool_calls": []},
            }

        def route(state: GraphState) -> str:
            """O roteador de entrada: é o que faz a retomada não repetir trabalho.
            Estado que já tem resposta (ou aprovação humana) não volta para o modelo."""
            if state.get(PENDING_ACTION_KEY):
                return END
            if state.get("output") is not None:
                return END
            if (state.get("scratch") or {}).get("tool_calls"):
                return "tools"
            return "think"

        graph.add_node("think", think)
        graph.add_node("tools", use_tools)
        graph.set_conditional_entry_point(route, {"think": "think", "tools": "tools", END: END})
        graph.add_conditional_edges("think", route, {"think": END, "tools": "tools", END: END})
        # Depois das ferramentas o modelo fala de novo, com o resultado em mãos — o teto
        # de 25 passos do runtime é quem impede a volta virar laço.
        graph.add_conditional_edges("tools", route, {"think": "think", "tools": END, END: END})
        return graph.compile()


BASE_AGENT = BaseAgentGraph()
register_graph_placeholder(BASE_AGENT)
