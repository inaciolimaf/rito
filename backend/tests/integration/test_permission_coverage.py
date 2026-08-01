from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute, iter_route_contexts

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
    # `iter_route_contexts` (fastapi.routing) resolve o caminho COM prefixo aplicado,
    # mesmo para rotas registradas via `include_router` — desde que o FastAPI passou a
    # envolver sub-routers incluídos num `_IncludedRouter` "preguiçoso" (spec 011,
    # Descobertas), `candidate_app.routes` deixou de conter `APIRoute` diretamente para
    # QUALQUER rota incluída via `include_router`, só para as registradas direto no app.
    # Um `isinstance(route, APIRoute)` sobre `candidate_app.routes` (a forma antiga deste
    # scanner) silenciosamente para de achar as rotas reais do app — passa vazio sempre,
    # não porque não há violação, mas porque não encontra rota nenhuma.
    for route_context in iter_route_contexts(candidate_app.routes):
        route = route_context.original_route
        if not isinstance(route, APIRoute):
            continue
        path = route_context.path
        if path is None or not path.startswith("/api/v1"):
            continue
        if any(path.startswith(prefix) for prefix in _EXEMPT_PREFIXES):
            continue
        calls = list(_iter_dependant_calls(route.dependant))
        if not any(is_permission_dependency(call) for call in calls):
            missing.append(f"{sorted(route_context.methods or [])} {path}")
    return missing


def test_every_domain_route_declares_a_permission() -> None:
    """Regra 5: nenhuma rota de /api/v1 (fora de /auth) nasce sem require_role/require_financial."""
    assert _routes_missing_permission(app) == []


def test_scanner_catches_a_route_without_permission() -> None:
    """Prova que o scanner pega o caso ruim — via `include_router`, igual `app.main` faz de
    verdade (spec 011, Descobertas: um probe_app com rotas registradas direto, sem
    include_router, não teria detectado o scanner quebrado)."""
    probe_router = APIRouter()

    @probe_router.get("/sem-permissao")
    async def unprotected() -> dict[str, bool]:
        return {"ok": True}

    @probe_router.get("/com-permissao", dependencies=[Depends(require_role(UserRole.GESTOR))])
    async def protected() -> dict[str, bool]:
        return {"ok": True}

    probe_app = FastAPI()
    probe_app.include_router(probe_router, prefix="/api/v1")

    missing = _routes_missing_permission(probe_app)

    assert any("/api/v1/sem-permissao" in item for item in missing)
    assert not any("/api/v1/com-permissao" in item for item in missing)
