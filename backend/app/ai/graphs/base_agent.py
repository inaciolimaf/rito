"""Grafo base reutilizável (spec 082 §2).

É o esqueleto que os agentes das specs 085+ herdam: um roteador de entrada que sabe
onde continuar (o que torna o grafo retomável), um nó que conversa com o modelo pela
camada 081 e uma saída. Ferramentas entram nas specs 083/084 — o nó `tools` já existe
e devolve o controle ao modelo, mas o registro de ferramentas chega vazio por enquanto.

Este é o único módulo que importa LangGraph no caminho de execução; ele é carregado
sob demanda (`app/ai/graphs/__init__.py` não importa nada).
"""

import json
from functools import partial
from typing import Any

from langgraph.graph import END, StateGraph

from app.ai.graphs.base import (
    PENDING_ACTION_KEY,
    GraphDeps,
    GraphState,
    register_graph_placeholder,
)
from app.ai.prompts import load_prompt
from app.integrations.openrouter.types import Message

# Spec 090, alvo 3: o texto mora em `app/ai/prompts/copilot.md`, versionado e revisável
# sem passar por dentro da lógica do grafo.
SYSTEM_PROMPT = load_prompt("copilot")


def _system_prompt(deps: GraphDeps) -> str:
    """Regra 1 da 085: a tela em que o usuário está entra no prompt.

    É o que faz "quanto esse cliente deve?" ser respondível na ficha do cliente sem o
    usuário repetir de quem está falando — o agente resolve o "esse" pelo contexto e
    confirma pelas ferramentas.
    """
    context = deps.context or {}
    linhas = []
    if context.get("route"):
        linhas.append(f"- Tela atual: {context['route']}")
    if context.get("lawsuit_id"):
        linhas.append(f"- Processo aberto na tela: {context['lawsuit_id']}")
    if context.get("customer_id"):
        linhas.append(f"- Cliente aberto na tela: {context['customer_id']}")
    if context.get("transaction_id"):
        linhas.append(f"- Lançamento aberto na tela: {context['transaction_id']}")
    if not linhas:
        return SYSTEM_PROMPT
    return (
        f"{SYSTEM_PROMPT}\n\nContexto da tela (use para resolver referências como "
        f"'este processo' ou 'esse cliente'):\n" + "\n".join(linhas)
    )


def _messages_for(state: GraphState, deps: GraphDeps) -> list[Message]:
    history = [Message(role="system", content=_system_prompt(deps))]
    for raw in state.get("messages") or []:
        history.append(
            Message(
                role=raw.get("role", "user"),
                content=raw.get("content") or "",
                tool_call_id=raw.get("tool_call_id") or None,
                name=raw.get("name"),
            )
        )
    pergunta = (state.get("input") or {}).get("question")
    # Só entra se ainda não estiver no histórico: numa volta com ferramenta, o modelo
    # precisa ver o RESULTADO como última mensagem — repetir a pergunta no fim empurraria
    # o resultado para o meio e convidaria o modelo a chamar a mesma ferramenta de novo.
    if pergunta and not any(
        item.role == "user" and item.content == str(pergunta) for item in history
    ):
        history.append(Message(role="user", content=str(pergunta)))
    return history


class BaseAgentGraph:
    """Roteador → modelo → fim, com o nó de ferramentas já no lugar."""

    name = "base_agent"
    feature_key = "copilot"

    def build(self, deps: GraphDeps) -> Any:
        """Monta o grafo. Os três nós são funções de módulo (spec 106): como closures,
        os ramos deles contavam para a complexidade de `build`, que só faz fiação — e
        função de fiação com complexidade 14 é o gate apontando para o lugar errado."""
        graph = StateGraph(GraphState)
        graph.add_node("think", partial(_think, deps=deps))
        graph.add_node("tools", partial(_use_tools, deps=deps))
        graph.set_conditional_entry_point(_route, {"think": "think", "tools": "tools", END: END})
        graph.add_conditional_edges("think", _route, {"think": END, "tools": "tools", END: END})
        # Depois das ferramentas o modelo fala de novo, com o resultado em mãos — o teto
        # de 25 passos do runtime é quem impede a volta virar laço.
        graph.add_conditional_edges("tools", _route, {"think": "think", "tools": END, END: END})
        return graph.compile()


async def _think(state: GraphState, *, deps: GraphDeps) -> dict[str, Any]:
    """Uma volta de conversa com o modelo. O `llm` é o `AiRunner` da 081: o modelo
    efetivo, o fallback e a contabilidade já vêm resolvidos de lá."""
    # A pergunta entra no histórico UMA vez, aqui: nas voltas seguintes o que precisa
    # estar por último é o resultado da ferramenta.
    messages = [*(state.get("messages") or [])]
    pergunta = (state.get("input") or {}).get("question")
    if pergunta and not any(
        item.get("role") == "user" and item.get("content") == str(pergunta) for item in messages
    ):
        messages.append({"role": "user", "content": str(pergunta)})
    response = await deps.llm.run(
        feature_key=deps.feature_key,
        messages=_messages_for({**state, "messages": messages}, deps),
        user_id=deps.user_id,
        tools=list(deps.tools.values()) or None,
    )
    if response.content:
        messages.append({"role": "assistant", "content": response.content})
    if not response.tool_calls:
        return {"messages": messages, "output": {"answer": response.content}}
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


async def _use_tools(state: GraphState, *, deps: GraphDeps) -> dict[str, Any]:
    """Executa o que o modelo pediu e devolve o resultado como mensagem de ferramenta
    (spec 083). Erro de ferramenta também volta como mensagem: o agente precisa poder se
    corrigir, não estourar."""
    pedidas = (state.get("scratch") or {}).get("tool_calls") or []
    scratch_limpo = {**(state.get("scratch") or {}), "tool_calls": []}
    if deps.tool_runner is None:
        return {
            "scratch": scratch_limpo,
            "output": {"answer": None, "unavailable_tools": [c["name"] for c in pedidas]},
        }
    deps.tool_runner.begin_step()
    messages, interrupcao = await _executar_ferramentas(state, deps, pedidas)
    if interrupcao is None or interrupcao.get("status") != "pending":
        return {"messages": messages, "scratch": scratch_limpo}
    return {
        "messages": messages,
        "scratch": scratch_limpo,
        PENDING_ACTION_KEY: {
            "kind": interrupcao["kind"],
            "title": interrupcao["title"],
            "preview": interrupcao["preview"],
            "description": None,
            "action_id": interrupcao["action_id"],
        },
    }


async def _executar_ferramentas(
    state: GraphState, deps: GraphDeps, pedidas: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Roda cada ferramenta pedida e devolve o histórico novo e a PRIMEIRA interrupção.

    Só a primeira importa: a partir dela o grafo para e espera a pessoa, então uma
    segunda proposta na mesma volta nunca chegaria à tela.
    """
    assert deps.tool_runner is not None
    messages = [*(state.get("messages") or [])]
    interrupcao: dict[str, Any] | None = None
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
        # Spec 084, regra 1: a ferramenta de escrita não gravou nada — ela propôs.
        # O grafo para aqui e espera a pessoa decidir.
        if interrupcao is None and result.get("pending_action"):
            interrupcao = result["pending_action"]
    return messages, interrupcao


def _route(state: GraphState) -> str:
    """O roteador de entrada: é o que faz a retomada não repetir trabalho. Estado que já
    tem resposta (ou aprovação humana) não volta para o modelo."""
    if state.get(PENDING_ACTION_KEY) or state.get("output") is not None:
        return END
    return "tools" if (state.get("scratch") or {}).get("tool_calls") else "think"


BASE_AGENT = BaseAgentGraph()
register_graph_placeholder(BASE_AGENT)
