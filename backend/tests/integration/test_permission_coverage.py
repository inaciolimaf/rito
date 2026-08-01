from collections.abc import Iterator
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute

from app.core.permissions import is_permission_dependency, require_role
from app.domain.users.models import UserRole
from app.main import app

# Prefixos isentos: /health não passa por /api/v1; /auth é pré-JWT (spec 004, ver Descobertas).
_EXEMPT_PREFIXES = ("/api/v1/auth",)


def _iter_dependant_calls(dependant: Any) -> Iterator[Any]:
    if dependant.call is not None:
        yield dependant.call
    for sub in dependant.dependencies:
        yield from _iter_dependant_calls(sub)


def _routes_missing_permission(candidate_app: FastAPI) -> list[str]:
    missing = []
    for route in candidate_app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith("/api/v1"):
            continue
        if any(route.path.startswith(prefix) for prefix in _EXEMPT_PREFIXES):
            continue
        calls = list(_iter_dependant_calls(route.dependant))
        if not any(is_permission_dependency(call) for call in calls):
            missing.append(f"{sorted(route.methods or [])} {route.path}")
    return missing


def test_every_domain_route_declares_a_permission() -> None:
    """Regra 5: nenhuma rota de /api/v1 (fora de /auth) nasce sem require_role/require_financial.

    Hoje não existe nenhuma rota de domínio além de /auth — isso passa vazio por enquanto,
    mas é o guarda-corpo para as 95 specs seguintes: rota nova sem declaração quebra este teste.
    """
    assert _routes_missing_permission(app) == []


def test_scanner_catches_a_route_without_permission() -> None:
    """Prova que o scanner de fato pega o caso ruim, não só o vazio de hoje."""
    probe_app = FastAPI()

    @probe_app.get("/api/v1/sem-permissao")
    async def unprotected() -> dict[str, bool]:
        return {"ok": True}

    @probe_app.get("/api/v1/com-permissao", dependencies=[Depends(require_role(UserRole.GESTOR))])
    async def protected() -> dict[str, bool]:
        return {"ok": True}

    missing = _routes_missing_permission(probe_app)

    assert any("/api/v1/sem-permissao" in item for item in missing)
    assert not any("/api/v1/com-permissao" in item for item in missing)
