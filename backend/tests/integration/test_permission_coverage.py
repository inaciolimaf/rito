from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute, iter_route_contexts

from app.core.permissions import is_permission_dependency, require_role
from app.domain.users.models import UserRole
from app.main import app
from app.public.deps import declared_scope, require_scope

# Prefixos isentos: /health não passa por /api/v1; /auth é pré-JWT (spec 004, ver Descobertas).
# /invitations/accept também é pré-JWT (spec 012) — só exige X-Tenant-Id, igual /auth,
# mas vive fora do prefixo /auth porque a spec declara a rota como recurso próprio.
_EXEMPT_PREFIXES = ("/api/v1/auth", "/api/v1/invitations/accept")

# Spec 134. A API pública era ponto cego deste gate: ele varre `/api/v1`, e as 22 rotas de
# `/api/public/v1` não declaram `require_role` (não há usuário de sessão ali) — declaram
# `require_scope`, que era uma dependência anônima. Rota pública nova sem escopo é rota
# aberta a qualquer token de qualquer integração, e agora reprova aqui.
PUBLIC_PREFIX = "/api/public/v1"

# O contrato da 095 §5. O número está escrito porque a lição do comentário de
# `_routes_missing_permission` vale em dobro aqui: um scanner que deixa de achar rota
# nenhuma passa vazio para sempre, e ninguém percebe.
ROTAS_PUBLICAS = 22


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


def _public_routes(candidate_app: FastAPI) -> list[tuple[str, str | None]]:
    """(rota, escopo declarado) de cada operação sob `/api/public/v1`.

    `openapi.json` fica de fora: ele vive noutro router, sem token, porque exigir escopo
    para LER a documentação impediria gerar cliente antes de pedir acesso (095, §9).
    """
    encontradas = []
    for route_context in iter_route_contexts(candidate_app.routes):
        route = route_context.original_route
        path = route_context.path
        if not isinstance(route, APIRoute) or path is None:
            continue
        if not path.startswith(PUBLIC_PREFIX) or path.endswith("/openapi.json"):
            continue
        escopos = [declared_scope(call) for call in _iter_dependant_calls(route.dependant)]
        declarado = next((escopo for escopo in escopos if escopo is not None), None)
        encontradas.append((f"{sorted(route_context.methods or [])} {path}", declarado))
    return encontradas


def test_toda_rota_da_api_publica_declara_um_escopo() -> None:
    """Spec 134: o gate passa a cobrir a superfície pública, que era o ponto cego dele."""
    rotas = _public_routes(app)

    assert len(rotas) == ROTAS_PUBLICAS, f"o scanner achou {len(rotas)} rotas públicas"
    assert [rota for rota, escopo in rotas if escopo is None] == []


def test_o_scanner_publico_pega_a_rota_sem_escopo() -> None:
    """Prova que ele morde — sem isto, "zero rotas sem escopo" seria indistinguível de
    "zero rotas encontradas"."""
    probe_router = APIRouter()

    @probe_router.get("/sem-escopo")
    async def sem_escopo() -> dict[str, bool]:
        return {"ok": True}

    @probe_router.get("/com-escopo", dependencies=[Depends(require_scope("read:customers"))])
    async def com_escopo() -> dict[str, bool]:
        return {"ok": True}

    probe_app = FastAPI()
    probe_app.include_router(probe_router, prefix=PUBLIC_PREFIX)

    rotas = dict(_public_routes(probe_app))

    assert rotas[f"['GET'] {PUBLIC_PREFIX}/sem-escopo"] is None
    assert rotas[f"['GET'] {PUBLIC_PREFIX}/com-escopo"] == "read:customers"


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
