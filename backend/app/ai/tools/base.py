"""Registry de ferramentas de leitura (spec 083).

O agente enxerga o escritório por aqui — e só por aqui. Três decisões carregam a spec
inteira:

1. **Sem RAG.** Nada de índice vetorial: a ferramenta consulta o banco na hora, então o
   agente nunca responde com dado velho de índice (CLAUDE.md §7, regra 3).
2. **A ferramenta roda como o usuário.** Mesma sessão, mesmo `app.tenant_id`, mesmo
   RBAC — o agente não tem privilégio próprio (regra 1). É por isso que `ToolContext`
   carrega a sessão da request, e não abre uma nova.
3. **Schema vem do Pydantic** (regra 9): o que o modelo recebe como contrato de
   argumentos é derivado do mesmo modelo que valida a chamada. Escrever o JSON Schema à
   mão criaria duas fontes de verdade que divergem no primeiro parâmetro novo.
"""

import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import FinancialAccess, UserRole
from app.domain.users.models import User
from app.integrations.openrouter.types import ToolSpec

# Regra 4: teto rígido de linhas por chamada.
MAX_ROWS = 50
# Regra 5: teto de tamanho da saída.
MAX_OUTPUT_BYTES = 20 * 1024
# Regra 11: chamadas de ferramenta por passo do grafo.
MAX_CALLS_PER_STEP = 10

_FINANCIAL_ORDER = {FinancialAccess.NONE: 0, FinancialAccess.READ_ONLY: 1, FinancialAccess.FULL: 2}
_ROLE_ORDER = {UserRole.COLABORADOR: 0, UserRole.ADMINISTRADOR: 1, UserRole.GESTOR: 2}


class ToolError(Exception):
    """Erro que o AGENTE precisa entender, não que derrube a execução (regra 8).

    Vira uma mensagem estruturada de volta para o modelo (`{"error": {...}}`), para ele
    poder se corrigir: pedir outro filtro, avisar o usuário que não tem permissão,
    tentar outra ferramenta.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_payload(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message}}


@dataclass
class ToolContext:
    """Tudo que uma ferramenta pode usar. Chega pronto do runner."""

    session: AsyncSession
    tenant_id: uuid.UUID
    user: User
    thread_id: uuid.UUID | None = None
    # De onde a conversa nasceu: tela, processo aberto, cliente aberto (get_current_context).
    screen_context: dict[str, Any] = field(default_factory=dict)


ParamsT = TypeVar("ParamsT", bound=BaseModel)
Handler = Callable[[ToolContext, Any], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    params_model: type[BaseModel]
    handler: Handler
    # Regra 2: ferramenta financeira exige acesso financeiro DO USUÁRIO.
    requires_financial: FinancialAccess = FinancialAccess.NONE
    requires_role: UserRole = UserRole.COLABORADOR

    def json_schema(self) -> dict[str, Any]:
        """Regra 9: derivado do Pydantic, nunca escrito à mão."""
        schema = self.params_model.model_json_schema()
        # `title`/`$defs` do Pydantic não agregam nada para o modelo e gastam tokens em
        # toda requisição — o que importa é properties/required.
        schema.pop("title", None)
        return schema

    def to_spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, parameters=self.json_schema())

    def check_permission(self, user: User) -> None:
        if _ROLE_ORDER[user.role] < _ROLE_ORDER[self.requires_role]:
            raise ToolError(
                "forbidden",
                f"O usuário não tem perfil {self.requires_role.value} para usar {self.name}.",
            )
        if _FINANCIAL_ORDER[user.financial_access] < _FINANCIAL_ORDER[self.requires_financial]:
            raise ToolError(
                "forbidden_financial",
                (
                    f"O usuário não tem acesso financeiro para usar {self.name}. "
                    "Explique isso a ele em vez de tentar outra ferramenta financeira."
                ),
            )


_REGISTRY: dict[str, ToolDef] = {}


def tool(
    *,
    name: str,
    description: str,
    requires_financial: FinancialAccess = FinancialAccess.NONE,
    requires_role: UserRole = UserRole.COLABORADOR,
) -> Callable[[Handler], Handler]:
    """Regra 12: registrar é decorar. O modelo de parâmetros sai da anotação do segundo
    argumento do handler — uma fonte de verdade só."""

    def decorator(handler: Handler) -> Handler:
        annotations = getattr(handler, "__annotations__", {})
        params_annotation = [
            value for key, value in annotations.items() if key not in ("ctx", "return")
        ]
        if not params_annotation or not isinstance(params_annotation[0], type):
            raise TypeError(f"{name}: o handler precisa anotar os parâmetros com um BaseModel.")
        params_model = params_annotation[0]
        if not issubclass(params_model, BaseModel):
            raise TypeError(f"{name}: os parâmetros precisam ser um BaseModel.")
        _REGISTRY[name] = ToolDef(
            name=name,
            description=description,
            params_model=params_model,
            handler=handler,
            requires_financial=requires_financial,
            requires_role=requires_role,
        )
        return handler

    return decorator


def get_tool(name: str) -> ToolDef:
    from app.ai.tools.loader import ensure_tools_loaded

    ensure_tools_loaded()
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise ToolError("unknown_tool", f"Ferramenta desconhecida: {name}.") from exc


def all_tools() -> list[ToolDef]:
    from app.ai.tools.loader import ensure_tools_loaded

    ensure_tools_loaded()
    return [_REGISTRY[name] for name in sorted(_REGISTRY)]


def tool_specs(user: User, *, include_write: bool = True) -> list[ToolSpec]:
    """O catálogo que vai para o modelo já é filtrado pelo RBAC do usuário: oferecer uma
    ferramenta que ele não pode usar só produz tentativa frustrada e token gasto.

    As de escrita (084) entram com a mesma descrição que a UI vai mostrar — e todas
    dizem "exige confirmação", porque é isso que acontece quando o modelo as chama.
    """
    specs = []
    for definition in all_tools():
        try:
            definition.check_permission(user)
        except ToolError:
            continue
        specs.append(definition.to_spec())
    if include_write:
        from app.ai.tools.write import all_write_tools

        specs.extend(
            ToolSpec(
                name=definition.name,
                description=definition.description,
                parameters=definition.json_schema(),
            )
            for definition in all_write_tools()
        )
    return specs


def truncate_rows(items: Sequence[Any], limit: int) -> tuple[list[Any], bool]:
    """Regra 4: acima do teto, corta e AVISA — o agente precisa saber que a lista está
    incompleta para pedir um filtro melhor, em vez de concluir por uma amostra."""
    capped = min(limit, MAX_ROWS)
    return list(items[:capped]), len(items) > capped
