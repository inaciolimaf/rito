import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuit_timeline import _seed_tribunal
from tests.integration.test_lawsuits import (
    _auth_header,
    _create_customer,
    _create_lawsuit,
    _create_lawsuit_type,
    _create_stage,
)

_NOW = datetime.now(UTC)
_THIS_MONTH = _NOW.date().replace(day=1)
_LAST_MONTH = (_THIS_MONTH - timedelta(days=1)).replace(day=1)


class LawsuitFactory:
    """Setup compartilhado: um gestor + tipo + etapa e atalhos para criar processos
    com atributos controlados (partes, datas, movimentações)."""

    def __init__(
        self,
        client: AsyncClient,
        app_session_factory: async_sessionmaker[AsyncSession],
        gestor: SeededUser,
        headers: dict[str, str],
        type_id: str,
        stage_id: str,
    ) -> None:
        self.client = client
        self.sessions = app_session_factory
        self.gestor = gestor
        self.headers = headers
        self.type_id = type_id
        self.stage_id = stage_id

    async def create(
        self, party_name: str | None = None, *, stage_id: str | None = None, **extra: object
    ) -> str:
        customer_id = await _create_customer(
            self.client, self.headers, party_name or f"Cliente {uuid.uuid4().hex[:8]}"
        )
        lawsuit = await _create_lawsuit(
            self.client,
            self.headers,
            user_id=str(self.gestor.user_id),
            lawsuit_type_id=self.type_id,
            stage_id=stage_id or self.stage_id,
            parties=[{"customer_id": customer_id, "pole": "ATIVO", "is_client": True}],
            **extra,
        )
        return str(lawsuit["id"])

    async def move(self, lawsuit_id: str, days_ago: int, title: str = "Andamento") -> None:
        await _seed_tribunal(
            self.sessions,
            self.gestor.tenant_id,
            lawsuit_id,
            title,
            _NOW - timedelta(days=days_ago),
        )

    async def backdate_created(self, lawsuit_id: str, created_at: datetime) -> None:
        async with self.sessions() as session, session.begin():
            await set_tenant_context(session, self.gestor.tenant_id)
            await session.execute(
                text("UPDATE lawsuits SET created_at = :ts WHERE id = CAST(:id AS uuid)"),
                {"ts": created_at, "id": lawsuit_id},
            )


async def _make_factory(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> LawsuitFactory:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    return LawsuitFactory(client, app_session_factory, gestor, headers, type_id, stage_id)


def _ids(body: dict[str, object]) -> set[str]:
    items = body["items"]
    assert isinstance(items, list)
    return {str(item["id"]) for item in items}


@pytest.fixture
async def factory(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> LawsuitFactory:
    return await _make_factory(client, make_user, app_session_factory)


# Cenário das 12 visões: cada processo cobre um caso distinto (regras 1–4).
async def _seed_view_scenario(factory: LawsuitFactory) -> dict[str, str]:
    scenario: dict[str, str] = {}
    scenario["sem_movimento"] = await factory.create("Sem Movimento")
    scenario["movido_hoje"] = await factory.create("Movido Hoje")
    await factory.move(scenario["movido_hoje"], 0)
    scenario["movido_40d"] = await factory.create("Movido 40 Dias")
    await factory.move(scenario["movido_40d"], 40)
    scenario["movido_100d"] = await factory.create("Movido 100 Dias")
    await factory.move(scenario["movido_100d"], 100)
    scenario["fechado_mes"] = await factory.create("Fechado Mês", closure_date=str(_THIS_MONTH))
    scenario["fechado_mes_passado"] = await factory.create(
        "Fechado Mês Passado", closure_date=str(_LAST_MONTH)
    )
    scenario["distribuido_mes"] = await factory.create(
        "Distribuído Mês", process_date=str(_THIS_MONTH)
    )
    scenario["arquivado_mes"] = await factory.create(
        "Arquivado Mês", closure_date=str(_LAST_MONTH), archived_date=str(_THIS_MONTH)
    )
    return scenario


_T = "sem_movimento"
_H = "movido_hoje"
_40 = "movido_40d"
_100 = "movido_100d"
_FM = "fechado_mes"
_FMP = "fechado_mes_passado"
_DM = "distribuido_mes"
_AM = "arquivado_mes"
_ALL = {_T, _H, _40, _100, _FM, _FMP, _DM, _AM}

# Regra 2: `active` exclui quem tem archived_date (fato processual), mesmo não arquivado.
_EXPECTED_VIEWS: dict[str, set[str]] = {
    "all": _ALL,
    "active": _ALL - {_AM},
    "moved_30d": {_H},
    "moved_7d": {_H},
    "moved_today": {_H},
    "never_captured": _ALL - {_H, _40, _100},
    "idle_30d": _ALL - {_H},
    "idle_45d": {_T, _100, _FM, _FMP, _DM, _AM},
    "idle_90d": {_T, _100, _FM, _FMP, _DM, _AM},
    "closed_this_month": {_FM},
    "filed_this_month": {_DM},
    "archived_this_month": {_AM},
}


@pytest.mark.parametrize("view", sorted(_EXPECTED_VIEWS))
async def test_doze_visoes(client: AsyncClient, factory: LawsuitFactory, view: str) -> None:
    scenario = await _seed_view_scenario(factory)
    response = await client.get(
        "/api/v1/lawsuits", params={"view": view, "limit": 50}, headers=factory.headers
    )
    assert response.status_code == 200
    found = _ids(response.json())
    expected = {scenario[key] for key in _EXPECTED_VIEWS[view]}
    assert found == expected, f"view={view}"


async def test_visao_e_filtro_combinam(client: AsyncClient, factory: LawsuitFactory) -> None:
    scenario = await _seed_view_scenario(factory)
    # Regra 1: visão é atalho, não exclusividade — active + q nasce AND.
    response = await client.get(
        "/api/v1/lawsuits",
        params={"view": "active", "q": "Fechado Mês Passado", "limit": 50},
        headers=factory.headers,
    )
    assert _ids(response.json()) == {scenario["fechado_mes_passado"]}


async def test_busca_textual_nas_quatro_fontes(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    por_parte = await factory.create("Zuleica da Busca")
    por_numero = await factory.create(process_number="0001234-34.2026.8.26.0100")
    por_protocolo = await factory.create(protocol_number="PROT-XY-998")
    por_pasta = await factory.create(folder="PastaGabarito")

    casos = {
        "zuleica": por_parte,
        "000123434": por_numero,
        "xy-998": por_protocolo,
        "gabarito": por_pasta,
    }
    for termo, esperado in casos.items():
        response = await client.get(
            "/api/v1/lawsuits", params={"q": termo, "limit": 50}, headers=factory.headers
        )
        assert _ids(response.json()) == {esperado}, f"q={termo}"


async def test_identification_casa_parte_contraria(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    contraria_id = await _create_customer(factory.client, factory.headers, "Contrária Documentada")
    # Define CPF direto no banco (o formulário de contato já foi testado na 018).
    async with factory.sessions() as session, session.begin():
        await set_tenant_context(session, factory.gestor.tenant_id)
        await session.execute(
            text("UPDATE customers SET identification = '11144477735' WHERE id = :id"),
            {"id": contraria_id},
        )
    lawsuit = await _create_lawsuit(
        factory.client,
        factory.headers,
        user_id=str(factory.gestor.user_id),
        lawsuit_type_id=factory.type_id,
        stage_id=factory.stage_id,
        parties=[
            {"customer_id": contraria_id, "pole": "CONTRARIA", "is_client": False},
        ],
    )

    # Regra 6: o CPF casa mesmo sendo da parte contrária, com ou sem máscara.
    for termo in ("11144477735", "111.444.777-35"):
        response = await client.get(
            "/api/v1/lawsuits",
            params={"identification": termo, "limit": 50},
            headers=factory.headers,
        )
        assert _ids(response.json()) == {str(lawsuit["id"])}


async def test_intervalo_com_um_lado_so(client: AsyncClient, factory: LawsuitFactory) -> None:
    antigo = await factory.create("Antigo")
    await factory.backdate_created(antigo, _NOW - timedelta(days=90))
    recente = await factory.create("Recente")

    # Regra 7: um lado só do intervalo é aceito.
    so_inicio = await client.get(
        "/api/v1/lawsuits",
        params={"created_from": str((_NOW - timedelta(days=7)).date()), "limit": 50},
        headers=factory.headers,
    )
    assert _ids(so_inicio.json()) == {recente}

    so_fim = await client.get(
        "/api/v1/lawsuits",
        params={"created_to": str((_NOW - timedelta(days=7)).date()), "limit": 50},
        headers=factory.headers,
    )
    assert _ids(so_fim.json()) == {antigo}


async def test_multivalorado_usa_or_interno(client: AsyncClient, factory: LawsuitFactory) -> None:
    outra_stage = await _create_stage(factory.client, factory.headers)
    na_stage_padrao = await factory.create("Na Etapa Padrão")
    na_outra_stage = await _create_lawsuit(
        factory.client,
        factory.headers,
        user_id=str(factory.gestor.user_id),
        lawsuit_type_id=factory.type_id,
        stage_id=outra_stage,
    )
    terceira_stage = await _create_stage(factory.client, factory.headers)
    na_terceira = await _create_lawsuit(
        factory.client,
        factory.headers,
        user_id=str(factory.gestor.user_id),
        lawsuit_type_id=factory.type_id,
        stage_id=terceira_stage,
    )

    # Regra 8: stage_id=a,b combina com OR entre os valores (e AND com o resto).
    response = await client.get(
        "/api/v1/lawsuits",
        params={"stage_id": f"{factory.stage_id},{outra_stage}", "limit": 50},
        headers=factory.headers,
    )
    assert _ids(response.json()) == {na_stage_padrao, str(na_outra_stage["id"])}
    assert str(na_terceira["id"]) not in _ids(response.json())


async def test_trigger_mantem_last_movement_at(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    lawsuit_id = await factory.create("Com Trigger")
    await factory.move(lawsuit_id, 10, "Movimento Antigo")
    await factory.move(lawsuit_id, 2, "Movimento Recente")
    # Um movimento mais antigo inserido DEPOIS não pode regredir o marcador (GREATEST).
    await factory.move(lawsuit_id, 30, "Movimento Tardio e Velho")

    response = await client.get(
        "/api/v1/lawsuits", params={"q": "Com Trigger", "limit": 50}, headers=factory.headers
    )
    (item,) = response.json()["items"]
    assert item["last_movement_title"] == "Movimento Recente"
    last_at = datetime.fromisoformat(item["last_movement_at"])
    assert abs((_NOW - timedelta(days=2)) - last_at) < timedelta(minutes=1)


async def test_listagem_dentro_do_budget_de_queries(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    for index in range(10):
        await factory.create(f"Budget {index}")
    await factory.move(await factory.create("Budget Movido"), 1)

    from sqlalchemy import event

    from app.domain.lawsuits.schemas import LawsuitFiltersQuery
    from app.domain.lawsuits.service import LawsuitService

    statements: list[str] = []
    async with factory.sessions() as session:
        bind = session.get_bind()

        @event.listens_for(bind, "before_cursor_execute", named=True)
        def count_statements(conn: object, cursor: object, statement: str, **kw: object) -> None:
            if "set_config" not in statement:
                statements.append(statement)

        service = LawsuitService(session=session, tenant_id=factory.gestor.tenant_id)
        async with session.begin():
            await set_tenant_context(session, factory.gestor.tenant_id)
            items, _cursor, total = await service.list_lawsuits(
                payload=LawsuitFiltersQuery(q="Budget"),
                order="desc",
                cursor=None,
                limit=20,
            )
            assert total == 11
            assert len(items) == 11

    # Budget (spec 026, regra 8, mantida aqui): contagem + página, com partes
    # agregadas e último andamento na mesma query — nunca 2 + 11.
    assert len(statements) <= 3


async def test_keyset_estavel(client: AsyncClient, factory: LawsuitFactory) -> None:
    for index in range(5):
        await factory.create(f"Keyset {index:02d}")

    seen: list[str] = []
    cursor: str | None = None
    while True:
        params: dict[str, str | int] = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        response = await client.get("/api/v1/lawsuits", params=params, headers=factory.headers)
        body = response.json()
        seen.extend(_ids(body))
        next_cursor = body["next_cursor"]
        cursor = str(next_cursor) if next_cursor else None
        if not cursor:
            break

    assert len(seen) == 5
    assert len(set(seen)) == 5


async def test_export_respeita_filtros(client: AsyncClient, factory: LawsuitFactory) -> None:
    await factory.create("Exportável Filtrado")
    await factory.create("Outro Qualquer")

    response = await client.post(
        "/api/v1/lawsuits/export",
        json={"format": "xlsx", "filters": {"view": "all", "q": "Exportável"}},
        headers=factory.headers,
    )
    assert response.status_code == 200
    assert "spreadsheetml" in response.headers["content-type"]

    from io import BytesIO

    from openpyxl import load_workbook

    sheet = load_workbook(BytesIO(response.content)).active
    assert sheet is not None
    rows = list(sheet.iter_rows(values_only=True))
    # Cabeçalho + 1 linha — o filtro de texto excluiu o "Outro Qualquer" (regra 10).
    assert len(rows) == 2
    assert rows[1][2] is None  # sem número; coluna Partes vem antes (célula vazia)
    assert "Exportável Filtrado" in str(rows[1][0])


async def test_listagem_isolada_entre_tenants(
    client: AsyncClient,
    factory: LawsuitFactory,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    await factory.create("Só do Tenant A")

    gestor_b = await make_user(role=UserRole.GESTOR)
    response = await client.get(
        "/api/v1/lawsuits", params={"limit": 50}, headers=_auth_header(gestor_b)
    )
    assert response.json()["items"] == []
    assert response.json()["total"] == 0
