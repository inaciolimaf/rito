"""Carrega os grafos sob demanda (spec 082).

Importar `langgraph`/`langchain_core` custa ~2 s. Fazer isso no import de `app.main`
faria toda request e todo worker de teste pagar por um agente que talvez nunca rode —
então o carregamento acontece na primeira vez que alguém pede um grafo.
"""

import importlib

# Módulos que registram grafos ao serem importados.
_GRAPH_MODULES = ("app.ai.graphs.base_agent",)

_loaded = False


def ensure_graphs_loaded() -> None:
    global _loaded
    if _loaded:
        return
    for module in _GRAPH_MODULES:
        importlib.import_module(module)
    _loaded = True
