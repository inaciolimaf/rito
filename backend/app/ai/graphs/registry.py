"""Registro de grafos disponíveis (spec 082).

Import de LangGraph acontece só aqui e nos módulos de grafo — nunca no caminho de
importação do `app.main`, porque `langchain_core` custa ~2 s de import e todo worker
de teste pagaria isso sem rodar um agente sequer.
"""

from app.ai.graphs.base import AgentGraph

_REGISTRY: dict[str, AgentGraph] = {}


class UnknownGraphError(Exception):
    """Nome de grafo que ninguém registrou → 422 na API."""


def register_graph(graph: AgentGraph) -> AgentGraph:
    _REGISTRY[graph.name] = graph
    return graph


def get_graph(name: str) -> AgentGraph:
    from app.ai.graphs.loader import ensure_graphs_loaded

    ensure_graphs_loaded()
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise UnknownGraphError(name) from exc


def graph_names() -> list[str]:
    from app.ai.graphs.loader import ensure_graphs_loaded

    ensure_graphs_loaded()
    return sorted(_REGISTRY)


def clear_registry() -> None:
    """Só para teste — o registro é global e um grafo de teste não pode vazar para
    outro arquivo de teste."""
    _REGISTRY.clear()
