from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException

from app.domain.auth.deps import get_current_user
from app.domain.users.models import FinancialAccess, User, UserRole

__all__ = [
    "FinancialAccess",
    "UserRole",
    "capabilities_for",
    "is_permission_dependency",
    "require_financial",
    "require_role",
]

# Hierarquia: GESTOR > ADMINISTRADOR > COLABORADOR (regra 1). require_role(ADMINISTRADOR)
# aceita GESTOR porque o número dele é maior.
_ROLE_ORDER: dict[UserRole, int] = {
    UserRole.COLABORADOR: 0,
    UserRole.ADMINISTRADOR: 1,
    UserRole.GESTOR: 2,
}

# NONE < READ_ONLY < FULL (regra 3). Uma rota GET declara require_financial(READ_ONLY)
# (READ_ONLY e FULL passam); uma rota de escrita declara require_financial(FULL) (só FULL passa).
_FINANCIAL_ORDER: dict[FinancialAccess, int] = {
    FinancialAccess.NONE: 0,
    FinancialAccess.READ_ONLY: 1,
    FinancialAccess.FULL: 2,
}

# Cumulativo por design: cada perfil inclui as capacidades do(s) de baixo (regra 1).
_ROLE_CAPABILITIES: dict[UserRole, frozenset[str]] = {
    UserRole.COLABORADOR: frozenset({"tasks.view", "tasks.complete"}),
    UserRole.ADMINISTRADOR: frozenset({"tasks.view", "tasks.complete", "users.manage"}),
    UserRole.GESTOR: frozenset(
        {
            "tasks.view",
            "tasks.complete",
            "users.manage",
            "settings.manage",
            "tasks.catalog.edit",
            "goals.manage",
            "taxonomies.manage",
        }
    ),
}

# Ortogonal ao perfil (regra 2): um Colaborador pode ter FULL, um Gestor pode ter NONE.
_FINANCIAL_CAPABILITIES: dict[FinancialAccess, frozenset[str]] = {
    FinancialAccess.NONE: frozenset(),
    FinancialAccess.READ_ONLY: frozenset({"financial.read"}),
    FinancialAccess.FULL: frozenset({"financial.read", "financial.write"}),
}


def capabilities_for(role: UserRole, financial_access: FinancialAccess) -> list[str]:
    """Derivado da matriz, nunca persistido (regra 7)."""
    caps = _ROLE_CAPABILITIES[role] | _FINANCIAL_CAPABILITIES[financial_access]
    return sorted(caps)


_PERMISSION_MARKER = "_rito_permission_dependency"


def require_role(minimum: UserRole) -> Callable[..., Awaitable[User]]:
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if _ROLE_ORDER[current_user.role] < _ROLE_ORDER[minimum]:
            raise HTTPException(
                status_code=403, detail=f"Exige perfil {minimum.value} ou superior."
            )
        return current_user

    setattr(_check, _PERMISSION_MARKER, True)
    return _check


def require_financial(minimum: FinancialAccess) -> Callable[..., Awaitable[User]]:
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if _FINANCIAL_ORDER[current_user.financial_access] < _FINANCIAL_ORDER[minimum]:
            raise HTTPException(
                status_code=403, detail=f"Exige acesso financeiro {minimum.value} ou superior."
            )
        return current_user

    setattr(_check, _PERMISSION_MARKER, True)
    return _check


def is_permission_dependency(call: object) -> bool:
    """Usado pelo teste de cobertura de permissão (regra 5) para achar rotas sem declaração."""
    return bool(getattr(call, _PERMISSION_MARKER, False))
