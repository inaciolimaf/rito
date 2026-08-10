"""DatajudService: alias, alerta de 401, descarte por sigilo e aviso de código
desconhecido (spec 046, §8) — a orquestração que o client puro não faz sozinho.
"""

import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.courts.models import Court
from app.domain.courts.repository import CourtRepository
from app.domain.datajud.exceptions import CourtNotSupportedError
from app.domain.datajud.service import DatajudService
from app.domain.integration_alerts.models import IntegrationAlert
from app.domain.users.models import UserRole
from app.integrations.datajud.client import DatajudClient, DatajudUnauthorizedError
from app.integrations.http.client import ResilientHttpClient
from tests.integration.conftest import SeededUser

SessionFactory = async_sessionmaker[AsyncSession]
FIXTURES = (
    Path(__file__).resolve().parents[1] / "fixtures" / "http" / "api-publica.datajud.cnj.jus.br"
)
API_KEY = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="


def fixture_response(name: str, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, content=(FIXTURES / name).read_bytes())


def make_service(session: AsyncSession, handler: httpx.MockTransport) -> DatajudService:
    http = ResilientHttpClient(transport=handler)
    client = DatajudClient(
        http=http, base_url="https://api-publica.datajud.cnj.jus.br", api_key=API_KEY
    )
    return DatajudService(session, client)


async def get_court(session: AsyncSession, code: str) -> Court:
    court = await CourtRepository(session).get_by_code(code)
    assert court is not None, f"tribunal {code} não está no seed da migration 021"
    return court


async def test_alias_resolvido_do_tribunal(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    seen_url = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_url
        seen_url = str(request.url)
        return fixture_response("tjsp_processo.json")

    async with app_session_factory() as session:
        await set_tenant_context(session, gestor.tenant_id)
        court = await get_court(session, "TJSP")
        service = make_service(session, httpx.MockTransport(handler))
        await service.fetch_process(court, "00001333920258260334")

    assert seen_url.startswith("https://api-publica.datajud.cnj.jus.br/api_publica_tjsp/_search")


async def test_tribunal_sem_alias_levanta_court_not_supported(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)

    async with app_session_factory() as session:
        await set_tenant_context(session, gestor.tenant_id)
        court = await get_court(session, "CNJ")  # regra 4: sem datajud_alias no seed
        assert court.datajud_alias is None
        service = make_service(
            session, httpx.MockTransport(lambda r: fixture_response("sem_hits.json"))
        )

        with pytest.raises(CourtNotSupportedError):
            await service.fetch_process(court, "00001333920258260334")


async def test_401_cria_alerta_critico_e_propaga(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    """Regra 3: alerta crítico de SISTEMA (`tenant_id` nulo) — a chave é config
    global. O erro propaga para o chamador decidir a pausa (047).

    Sem `session.begin()` de propósito: `IntegrationAlertRepository.create` só dá
    flush, nunca commit — a leitura de volta enxerga o INSERT na mesma
    transação, e fechar a sessão sem commitar não deixa o alerta de SISTEMA
    (visível a QUALQUER tenant pela política da migration 046) vazando para os
    demais testes/execuções que compartilham o `rito_test`."""
    gestor = await make_user(role=UserRole.GESTOR)

    async with app_session_factory() as session:
        await set_tenant_context(session, gestor.tenant_id)
        court = await get_court(session, "TJSP")
        handler = httpx.MockTransport(
            lambda r: fixture_response("401_chave_invalida.json", status_code=401)
        )
        service = make_service(session, handler)

        with pytest.raises(DatajudUnauthorizedError):
            await service.fetch_process(court, "00001333920258260334")

        alert = (await session.scalars(select(IntegrationAlert))).one()
        assert alert.tenant_id is None
        assert alert.integration == "datajud"
        assert alert.severity == "critical"
        assert alert.code == "api_key_rotated"


async def test_nivel_sigilo_maior_que_zero_e_descartado(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    """Regra 6: processo em segredo de justiça não é persistido — `fetch_process`
    devolve `None` sem erro."""
    gestor = await make_user(role=UserRole.GESTOR)
    payload = json.loads((FIXTURES / "tjsp_processo.json").read_text(encoding="utf-8"))
    payload["hits"]["hits"][0]["_source"]["nivelSigilo"] = 1
    body = json.dumps(payload).encode()

    async with app_session_factory() as session:
        await set_tenant_context(session, gestor.tenant_id)
        court = await get_court(session, "TJSP")
        service = make_service(
            session, httpx.MockTransport(lambda r: httpx.Response(200, content=body))
        )

        result = await service.fetch_process(court, "00001333920258260334")

    assert result is None


async def test_codigo_de_movimento_desconhecido_persiste_com_aviso(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: SessionFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regra 7: código fora do seed é aceito no `ParsedProcess` — só loga aviso."""
    gestor = await make_user(role=UserRole.GESTOR)
    payload = json.loads((FIXTURES / "tjsp_processo.json").read_text(encoding="utf-8"))
    payload["hits"]["hits"][0]["_source"]["movimentos"] = [
        {
            "codigo": 999999,
            "nome": "Movimento Inventado Para Teste",
            "dataHora": "2026-08-10T10:00:00.000Z",
        }
    ]
    body = json.dumps(payload).encode()

    async with app_session_factory() as session:
        await set_tenant_context(session, gestor.tenant_id)
        court = await get_court(session, "TJSP")
        service = make_service(
            session, httpx.MockTransport(lambda r: httpx.Response(200, content=body))
        )

        with caplog.at_level(logging.WARNING, logger="rito.datajud"):
            result = await service.fetch_process(court, "00001333920258260334")

    assert result is not None
    assert result.movements[0].code == 999999  # aceito, não filtrado
    assert any("999999" in record.message for record in caplog.records)
