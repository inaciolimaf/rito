"""Contratos dos grafos de agente (spec 082 §5).

O grafo é escrito com LangGraph (`StateGraph`), mas quem o executa é o
`GraphRuntime` (`app/ai/runtime.py`) — é ele que dá checkpoint, limite de passos,
timeout, cancelamento e registro de passo. Um grafo só declara nós e arestas.

**Grafos daqui são retomáveis por construção**: o primeiro nó é sempre um roteador que
olha o estado e decide por onde entrar. É isso que faz `resume` funcionar depois de uma
interrupção humana ou de uma falha no meio, sem repetir o que já rodou (regras 1 e 2).
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Protocol, TypedDict

GraphStatus = Literal["done", "waiting_human", "error"]

# Nome reservado do campo de estado que sinaliza interrupção: qualquer nó que o
# preencha faz o runtime parar e esperar o humano (regra 2).
PENDING_ACTION_KEY = "pending_action"


class GraphState(TypedDict, total=False):
    """Estado do grafo. É JSON puro de propósito: vai inteiro para `ai_checkpoints`,
    onde precisa ser legível por um humano em auditoria (regra 7)."""

    input: dict[str, Any]
    scratch: dict[str, Any]
    messages: list[dict[str, Any]]
    output: dict[str, Any] | None
    pending_action: dict[str, Any] | None
    approved: bool | None
    human_input: dict[str, Any] | None
    error: str | None


@dataclass(frozen=True)
class PendingAction:
    """O que o agente quer fazer e está esperando um humano confirmar (regra 2).

    `kind` identifica a ferramenta de escrita (084); `preview` é o que a UI mostra no
    `AIActionPreview` antes de o usuário aprovar.
    """

    kind: str
    title: str
    preview: dict[str, Any] = field(default_factory=dict)
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GraphResult:
    status: GraphStatus
    output: dict[str, Any] | None = None
    pending_action: dict[str, Any] | None = None
    error: str | None = None


@dataclass(frozen=True)
class GraphDeps:
    """O que um nó pode usar. Chega pronto do runtime — nenhum nó abre sessão, monta
    client de LLM ou lê configuração por conta própria (DIP, CLAUDE.md §5).

    `llm` é o `AiRunner` da 081 (modelo por feature, fallback e contabilidade já
    resolvidos); `tools` chega vazio aqui e é preenchido pelas specs 083/084.
    """

    tenant_id: "uuid.UUID"
    user_id: "uuid.UUID | None"
    llm: Any
    feature_key: str
    # Catálogo oferecido ao modelo (já filtrado pelo RBAC do usuário, spec 083) e o
    # runner que executa a chamada — nenhum nó fala com o banco por conta própria.
    tools: dict[str, Any] = field(default_factory=dict)
    tool_runner: Any = None
    context: dict[str, Any] = field(default_factory=dict)


class AgentGraph(Protocol):
    """Um grafo registrado. `build(deps)` devolve o grafo COMPILADO do LangGraph."""

    name: str
    feature_key: str

    def build(self, deps: GraphDeps) -> Any: ...


NodeFn = Callable[[GraphState], Awaitable[dict[str, Any]]]


def interrupt_for(action: PendingAction) -> dict[str, Any]:
    """Açúcar para o nó que pede confirmação: devolver isto interrompe o grafo."""
    return {PENDING_ACTION_KEY: action.to_dict()}


def is_interrupted(state: GraphState) -> bool:
    return state.get(PENDING_ACTION_KEY) is not None


def register_graph_placeholder(graph: AgentGraph) -> AgentGraph:
    """Registro tardio: o módulo do grafo se registra ao ser importado, e quem importa
    é `app/ai/graphs/loader.py` — assim o custo de importar LangGraph só acontece se
    alguém for de fato executar um agente."""
    from app.ai.graphs.registry import register_graph

    return register_graph(graph)
