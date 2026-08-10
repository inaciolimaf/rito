"""Termos monitorados: CRUD, validações, pausa, sync manual e RLS (spec 043, §8)."""

import json
import uuid
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.core.tokens import create_access_token
from app.domain.monitored_terms.models import MonitoredTerm
from app.domain.monitored_terms.repository import MonitoredTermRepository
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser

SessionFactory = async_sessionmaker[AsyncSession]
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "http" / "comunicaapi.pje.jus.br"

VALID_CPF = "529.982.247-25"
VALID_CNPJ = "11.444.777/0001-61"


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


async def _create_term(
    client: AsyncClient, headers: dict[str, str], payload: Mapping[str, object]
) -> dict[str, object]:
    response = await client.post("/api/v1/monitored-terms", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


async def test_crud_dos_tres_tipos(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    admin = await make_user(role=UserRole.ADMINISTRADOR, tenant_id=gestor.tenant_id)
    gestor_headers = _auth_header(gestor)

    oab = await _create_term(
        client, gestor_headers, {"kind": "OAB", "value": "114962", "oab_state": "mg"}
    )
    assert oab["status"] == "PENDENTE"  # regra 5
    assert oab["oab_state"] == "MG"
    # Regra 6: backfill padrão de 30 dias.
    assert oab["backfill_from"] == str(date.today() - timedelta(days=30))
    assert oab["next_sync_at"] is not None

    cpf = await _create_term(client, gestor_headers, {"kind": "CPF", "value": VALID_CPF})
    assert cpf["value"] == "52998224725"  # só dígitos

    cnpj = await _create_term(client, gestor_headers, {"kind": "CNPJ", "value": VALID_CNPJ})
    assert cnpj["value"] == "11444777000161"

    updated = await client.put(
        f"/api/v1/monitored-terms/{oab['id']}",
        json={"label": "OAB do sócio", "user_id": None, "backfill_from": None, "is_active": True},
        headers=gestor_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["label"] == "OAB do sócio"

    listing = await client.get("/api/v1/monitored-terms", headers=_auth_header(admin))
    assert listing.status_code == 200
    assert listing.json()["total"] == 3

    filtered = await client.get("/api/v1/monitored-terms?kind=CPF", headers=_auth_header(admin))
    assert [item["kind"] for item in filtered.json()["items"]] == ["CPF"]

    deleted = await client.delete(f"/api/v1/monitored-terms/{cnpj['id']}", headers=gestor_headers)
    assert deleted.status_code == 204
    listing = await client.get("/api/v1/monitored-terms", headers=_auth_header(admin))
    assert listing.json()["total"] == 2


async def test_oab_sem_uf_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    response = await client.post(
        "/api/v1/monitored-terms",
        json={"kind": "OAB", "value": "114962"},
        headers=_auth_header(gestor),
    )
    assert response.status_code == 422


async def test_cpf_invalido_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    response = await client.post(
        "/api/v1/monitored-terms",
        json={"kind": "CPF", "value": "111.111.111-11"},
        headers=_auth_header(gestor),
    )
    assert response.status_code == 422


async def test_termo_duplicado_no_tenant_retorna_409(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    payload = {"kind": "OAB", "value": "114962", "oab_state": "MG"}
    await _create_term(client, headers, payload)

    response = await client.post("/api/v1/monitored-terms", json=payload, headers=headers)
    assert response.status_code == 409

    # Mas a MESMA OAB em outra UF é um termo diferente (a unique inclui oab_state).
    other_state = await client.post(
        "/api/v1/monitored-terms",
        json={"kind": "OAB", "value": "114962", "oab_state": "SP"},
        headers=headers,
    )
    assert other_state.status_code == 201


async def test_mesmo_termo_em_outro_tenant_e_aceito(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 3: a duplicidade é por tenant — OABs de escritórios diferentes colidem
    no DJEN, não no Rito."""
    payload = {"kind": "OAB", "value": "114962", "oab_state": "MG"}
    gestor_a = await make_user(role=UserRole.GESTOR)
    gestor_b = await make_user(role=UserRole.GESTOR)

    await _create_term(client, _auth_header(gestor_a), payload)
    created_b = await client.post(
        "/api/v1/monitored-terms", json=payload, headers=_auth_header(gestor_b)
    )
    assert created_b.status_code == 201


async def test_backfill_acima_de_12_meses_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    response = await client.post(
        "/api/v1/monitored-terms",
        json={
            "kind": "CPF",
            "value": VALID_CPF,
            "backfill_from": str(date.today() - timedelta(days=400)),
        },
        headers=_auth_header(gestor),
    )
    assert response.status_code == 422


async def test_pausar_tira_do_agendamento_e_retomar_devolve(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: SessionFactory,
) -> None:
    """Regra 7: pausado sai do list_due (o predicado do índice ix_terms_due); o
    histórico e o termo continuam lá."""
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    term = await _create_term(
        client, headers, {"kind": "OAB", "value": "114962", "oab_state": "MG"}
    )

    async def due_ids() -> set[uuid.UUID]:
        async with app_session_factory() as session, session.begin():
            await set_tenant_context(session, gestor.tenant_id)
            repository = MonitoredTermRepository(session)
            return {item.id for item in await repository.list_due(datetime.now(UTC))}

    assert uuid.UUID(str(term["id"])) in await due_ids()

    paused = await client.post(f"/api/v1/monitored-terms/{term['id']}/pause", headers=headers)
    assert paused.status_code == 200
    assert paused.json()["status"] == "PAUSADO"
    assert uuid.UUID(str(term["id"])) not in await due_ids()

    # Pausar de novo é transição inválida.
    again = await client.post(f"/api/v1/monitored-terms/{term['id']}/pause", headers=headers)
    assert again.status_code == 409

    resumed = await client.post(f"/api/v1/monitored-terms/{term['id']}/resume", headers=headers)
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "PENDENTE"  # nunca sincronizou → não volta ATIVO
    assert uuid.UUID(str(term["id"])) in await due_ids()


async def test_excluir_termo_preserva_publicacoes(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: SessionFactory,
) -> None:
    """Regra 8: publications não referenciam o termo — excluir não apaga o capturado."""
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    term = await _create_term(
        client, headers, {"kind": "OAB", "value": "114962", "oab_state": "MG"}
    )
    item = json.loads((FIXTURES / "oab_mg.json").read_text(encoding="utf-8"))["items"][0]
    created = await client.post("/api/v1/publications", json={"item": item}, headers=headers)
    assert created.status_code == 201

    deleted = await client.delete(f"/api/v1/monitored-terms/{term['id']}", headers=headers)
    assert deleted.status_code == 204

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, gestor.tenant_id)
        count = await session.scalar(text("SELECT count(*) FROM publications"))
        assert count == 1


async def test_sync_manual_concorrente_retorna_409(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 10: uma execução aberta por termo; a segunda pede 409. A primeira fica
    registrada no histórico (runs)."""
    gestor = await make_user(role=UserRole.GESTOR)
    admin = await make_user(role=UserRole.ADMINISTRADOR, tenant_id=gestor.tenant_id)
    admin_headers = _auth_header(admin)
    term = await _create_term(
        client, _auth_header(gestor), {"kind": "OAB", "value": "114962", "oab_state": "MG"}
    )

    first = await client.post(f"/api/v1/monitored-terms/{term['id']}/sync", headers=admin_headers)
    assert first.status_code == 202

    second = await client.post(f"/api/v1/monitored-terms/{term['id']}/sync", headers=admin_headers)
    assert second.status_code == 409

    runs = await client.get(f"/api/v1/monitored-terms/{term['id']}/runs", headers=admin_headers)
    assert runs.status_code == 200
    assert runs.json()["total"] == 1
    assert runs.json()["items"][0]["finished_at"] is None


async def test_colaborador_recebe_403(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador = await make_user(role=UserRole.COLABORADOR)
    headers = _auth_header(colaborador)

    response = await client.post(
        "/api/v1/monitored-terms",
        json={"kind": "CPF", "value": VALID_CPF},
        headers=headers,
    )
    assert response.status_code == 403

    listing = await client.get("/api/v1/monitored-terms", headers=headers)
    assert listing.status_code == 403


async def test_rls_termo_de_um_tenant_nao_aparece_para_outro(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: SessionFactory,
) -> None:
    gestor_a = await make_user(role=UserRole.GESTOR)
    gestor_b = await make_user(role=UserRole.GESTOR)
    await _create_term(
        client,
        _auth_header(gestor_a),
        {"kind": "OAB", "value": "114962", "oab_state": "MG"},
    )

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, gestor_b.tenant_id)
        visible = (await session.scalars(select(MonitoredTerm))).all()
        assert visible == []
