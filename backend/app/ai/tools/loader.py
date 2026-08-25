"""Carrega os módulos de ferramenta sob demanda (spec 083, regra 12).

Mesmo motivo do loader de grafos: o registro se monta por import, e importar tudo no
`app.main` faria toda request pagar por um catálogo que só o agente usa.
"""

import importlib

_TOOL_MODULES = (
    "app.ai.tools.read_customers",
    "app.ai.tools.read_lawsuits",
    "app.ai.tools.read_tasks",
    "app.ai.tools.read_financial",
    "app.ai.tools.read_analytics",
)

_loaded = False


def ensure_tools_loaded() -> None:
    global _loaded
    if _loaded:
        return
    for module in _TOOL_MODULES:
        importlib.import_module(module)
    _loaded = True
