"""Auditoria de resiliência de verdade das integrações CNJ (spec 050).

Seis cenários de caos do alvo 2, cada um virando teste permanente:
recuperação sozinha após defeito prolongado, pausa sem loop num 401
permanente, resposta malformada, timeout no meio da paginação, relógio fora
de sincronia e ausência de transação/lock preso após falha externa. Também
cobre o ganho concreto do alvo 1 (DataJud com histórico de execução) e um
gap de cobertura achado na auditoria do §5 (isolamento de tenant em
`lawsuit_subjects`, tabela nova da spec 047 sem teste de RLS dedicado).

Nenhuma chamada de rede de verdade — `httpx.MockTransport` simula as
respostas (inclusive timeout/JSON truncado), como em 041/044/046/047.
"""

import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import cast

import httpx
from redis.asyncio import Redis
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.locks import RedisSyncLock
from app.core.redis import create_redis_client
from app.core.rls import set_tenant_context
from app.domain.datajud.movement_sync_service import MovementSyncService
from app.domain.datajud.service import DatajudService
from app.domain.integration_alerts.models import IntegrationAlert
from app.domain.lawsuits.models import LawsuitSubject
from app.domain.monitored_terms.models import MonitoredTerm, TermStatus, TermSyncRun
from app.domain.monitored_terms.repository import TermSyncRunRepository
from app.domain.monitored_terms.sync import PublicationPage, TermSyncService
from app.domain.publications.models import Publication
from app.domain.users.models import UserRole
from app.integrations.datajud.client import DatajudClient
from app.integrations.djen.client import DjenClient
from app.integrations.djen.source import DjenPublicationSource
from app.integrations.http.client import ResilientHttpClient
from tests.clock import dia_do_escritorio
from tests.integration.conftest import SeededUser
from tests.integration.test_datajud_movement_sync import (
    API_KEY as DATAJUD_API_KEY,
)
from tests.integration.test_datajud_movement_sync import (
    BASE_URL as DATAJUD_BASE_URL,
)
from tests.integration.test_datajud_movement_sync import (
    SyncSetup,
    _cnj,
    get_lawsuit,
)
from tests.integration.test_datajud_movement_sync import setup as setup  # noqa: F401 (fixture)
from tests.integration.test_djen_sync import make_term
from tests.integration.test_lawsuits import (
    _auth_header,
    _create_lawsuit,
    _create_lawsuit_type,
    _create_stage,
)

SessionFactory = async_sessionmaker[AsyncSession]
DJEN_BASE_URL = "https://comunicaapi.pje.jus.br/api/v1"
DJEN_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "http" / "comunicaapi.pje.jus.br"


async def _no_sleep(seconds: float) -> None:
    pass


def _djen_source(handler: httpx.MockTransport) -> DjenPublicationSource:
    http = ResilientHttpClient(transport=handler, sleep=_no_sleep)
    client = DjenClient(http=http, base_url=DJEN_BASE_URL, user_agent="pytest")
    return DjenPublicationSource(client)


def _one_item_payload() -> dict[str, object]:
    # cast: json.loads devolve Any — o shape real é validado pelo fixture em si
    # (mesmo item usado em test_djen_sync.py::fixture_items).
    payload = cast(
        dict[str, object], json.loads((DJEN_FIXTURES / "oab_mg.json").read_text(encoding="utf-8"))
    )
    payload["items"] = cast(list[object], payload["items"])[:1]
    payload["count"] = 1
    return payload


async def _publication_count(factory: SessionFactory, tenant_id: uuid.UUID) -> int:
    async with factory() as session:
        await set_tenant_context(session, tenant_id)
        total = await session.scalar(select(func.count()).select_from(Publication))
        return total or 0


# ---- 1. DJEN 500 persistente e depois recupera sozinho -------------------------------


async def test_djen_500_recupera_apos_falhas_seguidas(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    term_id = await make_term(app_session_factory, tenant_id)

    def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "fora do ar"})

    async with app_session_factory() as session:
        await set_tenant_context(session, tenant_id)
        source = _djen_source(httpx.MockTransport(failing_handler))
        service = TermSyncService(session, tenant_id, source)
        for _ in range(3):  # "por 1 hora": 3 tentativas seguidas do beat diário falham
            term = await session.get(MonitoredTerm, term_id)
            assert term is not None
            await service.sync_term(term)

    async with app_session_factory() as session:
        await set_tenant_context(session, tenant_id)
        term = await session.get(MonitoredTerm, term_id)
        assert term is not None
        assert term.status is TermStatus.FALHA
        assert term.consecutive_failures == 3
        assert term.alert_id is not None  # spec 049: 3 falhas seguidas abrem alerta

    def recovered_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_one_item_payload())

    async with app_session_factory() as session:
        await set_tenant_context(session, tenant_id)
        source = _djen_source(httpx.MockTransport(recovered_handler))
        service = TermSyncService(session, tenant_id, source)
        term = await session.get(MonitoredTerm, term_id)
        assert term is not None
        run = await service.sync_term(term)

    assert run is not None and run.error is None
    async with app_session_factory() as session:
        await set_tenant_context(session, tenant_id)
        term = await session.get(MonitoredTerm, term_id)
        assert term is not None
        assert term.status is TermStatus.ATIVO
        assert term.consecutive_failures == 0
        assert term.alert_id is None  # resolvido (spec 049, regra 3)
        alert = await session.scalar(
            select(IntegrationAlert).where(IntegrationAlert.tenant_id == tenant_id)
        )
        assert alert is not None and alert.resolved_at is not None


# ---- 2. DataJud 401 permanente: para o lote, não insiste por processo ----------------


async def test_datajud_401_permanente_para_o_lote_sem_duplicar_alerta(
    setup: SyncSetup,
) -> None:
    await setup.create_lawsuit(process_number=_cnj(901))
    second_id = await setup.create_lawsuit(process_number=_cnj(902))

    def unauthorized_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "chave inválida"})

    async with setup.sessions() as session, session.begin():
        await set_tenant_context(session, setup.gestor.tenant_id)
        http = ResilientHttpClient(
            transport=httpx.MockTransport(unauthorized_handler), sleep=_no_sleep
        )
        datajud_client = DatajudClient(
            http=http, base_url=DATAJUD_BASE_URL, api_key=DATAJUD_API_KEY
        )
        datajud_service = DatajudService(session, datajud_client)
        service = MovementSyncService(session, setup.gestor.tenant_id, datajud_service)
        results = await service.sync_due(batch_size=10)

    # Regra do alvo 2: o lote PARA no primeiro 401 — o segundo processo nunca é tentado.
    assert len(results) == 1
    assert results[0].status == "error"

    async with setup.sessions() as session:
        await set_tenant_context(session, setup.gestor.tenant_id)
        alerts = (await session.scalars(select(IntegrationAlert))).all()
        assert len(alerts) == 1  # dedup: não um alerta por processo
        assert alerts[0].code == "api_key_rotated"
        assert alerts[0].severity == "critical"
    second = await get_lawsuit(setup.sessions, setup.gestor.tenant_id, second_id)
    assert second.datajud_last_sync_at is None  # nunca chegou a ser tentado

    # Limpeza: este teste (diferente dos demais que tocam IntegrationAlert nesta
    # suíte) usa `session.begin()` de propósito — precisa READ BACK numa sessão
    # separada (regra acima) — então o alerta de SISTEMA (tenant_id nulo, visível a
    # QUALQUER tenant pela política da migration 046) É COMMITADO de verdade, ao
    # contrário do padrão "só flush" usado em test_datajud_service.py/test_sync_
    # observability.py. Sem apagar aqui, o alerta vaza pro resto da suíte que rodar
    # depois no mesmo `rito_test` — achado real ao fechar a spec 060 (não é dívida
    # do produto, é higiene de teste; ver docs/DECISOES.md).
    async with setup.sessions() as session, session.begin():
        await set_tenant_context(session, setup.gestor.tenant_id)
        await session.execute(delete(IntegrationAlert).where(IntegrationAlert.tenant_id.is_(None)))


# ---- Alvo 1: DataJud ganha histórico de execução (sync_runs unificado) --------------


async def test_datajud_ganha_historico_de_execucao_sucesso_e_erro(setup: SyncSetup) -> None:
    """Spec 050, alvo 1: `sync_runs` (antes só do DJEN) agora fecha uma linha por
    execução do DataJud também — sucesso e erro, sempre com `finished_at`."""
    ok_id = await setup.create_lawsuit(process_number=_cnj(950))
    bad_id = await setup.create_lawsuit(process_number=_cnj(951))
    good_payload = {"hits": {"total": {"value": 0}, "hits": []}}
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json=good_payload)
        raise httpx.TimeoutException("timeout simulado")

    async with setup.sessions() as session, session.begin():
        await set_tenant_context(session, setup.gestor.tenant_id)
        http = ResilientHttpClient(transport=httpx.MockTransport(handler), sleep=_no_sleep)
        datajud_client = DatajudClient(
            http=http, base_url=DATAJUD_BASE_URL, api_key=DATAJUD_API_KEY
        )
        datajud_service = DatajudService(session, datajud_client)
        service = MovementSyncService(session, setup.gestor.tenant_id, datajud_service)
        results = await service.sync_due(batch_size=10)

    assert {r.lawsuit_id for r in results} == {ok_id, bad_id}
    by_id = {r.lawsuit_id: r for r in results}
    assert by_id[ok_id].status == "not_found"
    assert by_id[bad_id].status == "error"

    async with setup.sessions() as session:
        await set_tenant_context(session, setup.gestor.tenant_id)
        runs = (
            await session.scalars(
                select(TermSyncRun)
                .where(TermSyncRun.integration == "datajud")
                .order_by(TermSyncRun.started_at)
            )
        ).all()
    assert len(runs) == 2
    by_lawsuit = {r.lawsuit_id: r for r in runs}
    assert by_lawsuit[ok_id].error is None and by_lawsuit[ok_id].finished_at is not None
    assert by_lawsuit[ok_id].term_id is None  # exclusivo — regra do CHECK ck_sync_runs_subject
    assert by_lawsuit[bad_id].error is not None and by_lawsuit[bad_id].finished_at is not None

    # Exposto via API — GET /lawsuits/{id}/sync-runs (novo nesta spec).
    response = await setup.client.get(f"/api/v1/lawsuits/{ok_id}/sync-runs", headers=setup.headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["error"] is None


# ---- 3. Resposta malformada não derruba o sync -----------------------------------------


async def test_resposta_malformada_nao_derruba_o_sync(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    term_id = await make_term(app_session_factory, tenant_id)

    def truncated_json_handler(request: httpx.Request) -> httpx.Response:
        # JSON de propósito quebrado no meio — response.json() levanta JSONDecodeError.
        return httpx.Response(200, content=b'{"count": 1, "items": [{"id": 1,')

    async with app_session_factory() as session:
        await set_tenant_context(session, tenant_id)
        source = _djen_source(httpx.MockTransport(truncated_json_handler))
        service = TermSyncService(session, tenant_id, source)
        term = await session.get(MonitoredTerm, term_id)
        assert term is not None
        run = await service.sync_term(term)

    assert run is not None and run.error is not None
    assert await _publication_count(app_session_factory, tenant_id) == 0

    def wrong_shape_handler(request: httpx.Request) -> httpx.Response:
        # JSON válido, mas item sem os campos obrigatórios (id/hash/data) — o parser
        # levanta DjenParseError em vez de aceitar um item incompleto calado.
        return httpx.Response(200, json={"count": 1, "items": [{"texto": "sem os campos certos"}]})

    async with app_session_factory() as session:
        await set_tenant_context(session, tenant_id)
        source = _djen_source(httpx.MockTransport(wrong_shape_handler))
        service = TermSyncService(session, tenant_id, source)
        term = await session.get(MonitoredTerm, term_id)
        assert term is not None
        run = await service.sync_term(term)

    assert run is not None and run.error is not None
    async with app_session_factory() as session:
        await set_tenant_context(session, tenant_id)
        term = await session.get(MonitoredTerm, term_id)
        assert term is not None
        assert term.status is TermStatus.FALHA  # regra 6 — nunca crasha o processo chamador
    assert await _publication_count(app_session_factory, tenant_id) == 0


# ---- 4. Timeout no meio da paginação não persiste a página parcial -------------------


async def test_timeout_no_meio_da_paginacao_nao_persiste_parcial(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    # 91 dias de backfill: 2 fatias de 90 dias (regra 12 da 044) — página 1 (fatia 1)
    # tem que persistir mesmo que a fatia 2 estoure em timeout.
    term_id = await make_term(app_session_factory, tenant_id, backfill_days=91)
    good_payload = _one_item_payload()
    calls = {"n": 0}

    def flaky_handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json=good_payload)  # fatia 1: sucesso, commita
        raise httpx.TimeoutException("timeout simulado na fatia 2")  # fatia 2: sempre estoura

    async with app_session_factory() as session:
        await set_tenant_context(session, tenant_id)
        source = _djen_source(httpx.MockTransport(flaky_handler))
        service = TermSyncService(session, tenant_id, source)
        term = await session.get(MonitoredTerm, term_id)
        assert term is not None
        run = await service.sync_term(term)

    assert run is not None and run.error is not None
    # A fatia 1 (página já commitada) fica; a fatia 2 (timeout) não deixou nada pela metade.
    assert await _publication_count(app_session_factory, tenant_id) == 1
    async with app_session_factory() as session:
        await set_tenant_context(session, tenant_id)
        term = await session.get(MonitoredTerm, term_id)
        assert term is not None
        assert term.status is TermStatus.FALHA
        assert term.last_captured_date is not None  # avançou até onde a fatia 1 foi


# ---- 5. Relógio fora de sincronia não trava nem processa janela absurda -------------


class _NeverCalledSource:
    """PublicationSource que falha o teste se for chamada (5a: janela invertida não
    deveria nem tentar buscar)."""

    async def fetch(
        self, *, term: MonitoredTerm, start: date, end: date, page: int
    ) -> PublicationPage:
        raise AssertionError("fetch não deveria ser chamado — janela invertida não itera")


async def test_relogio_atrasado_nao_trava_so_gera_sync_vazio(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    """`now` ANTES de `last_captured_date` (relógio do host atrasado) — a janela
    fica invertida (`start > today`) e o `while` não deveria nunca iterar; o sync
    tem que fechar limpo, não travar nem levantar."""
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    captured = date(2026, 8, 1)
    term_id = await make_term(app_session_factory, tenant_id, last_captured_date=captured)
    skewed_now = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)  # "atrasado" 17 dias

    async with app_session_factory() as session:
        await set_tenant_context(session, tenant_id)
        service = TermSyncService(session, tenant_id, _NeverCalledSource())
        term = await session.get(MonitoredTerm, term_id)
        assert term is not None
        run = await service.sync_term(term, now=skewed_now)

    assert run is not None and run.error is None and run.found_count == 0
    async with app_session_factory() as session:
        await set_tenant_context(session, tenant_id)
        term = await session.get(MonitoredTerm, term_id)
        assert term is not None
        assert term.status is TermStatus.ATIVO  # não trava, não crasha — só não avança


async def test_relogio_adiantado_fatia_em_janelas_limitadas(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    """`now` bem à frente do real (relógio adiantado) — a janela fica enorme, mas
    o fatiamento de 90 dias (regra 12 da 044) já limita: número de chamadas é
    previsível, o sync termina (não é um `while` sem fim)."""
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    term_id = await make_term(app_session_factory, tenant_id, backfill_days=10)
    skewed_now = datetime.now(UTC) + timedelta(days=400)  # mais de 1 ano adiantado

    def empty_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"count": 0, "items": []})

    async with app_session_factory() as session:
        await set_tenant_context(session, tenant_id)
        source = _djen_source(httpx.MockTransport(empty_handler))
        service = TermSyncService(session, tenant_id, source)
        term = await session.get(MonitoredTerm, term_id)
        assert term is not None
        run = await service.sync_term(term, now=skewed_now)

    assert run is not None and run.error is None
    async with app_session_factory() as session:
        await set_tenant_context(session, tenant_id)
        term = await session.get(MonitoredTerm, term_id)
        assert term is not None
        assert term.status is TermStatus.ATIVO
        assert term.last_captured_date == dia_do_escritorio(skewed_now)  # fechou, não travou


# ---- 6. Falha externa nunca deixa lock preso nem sessão poluída ---------------------


async def test_falha_externa_nao_deixa_lock_preso_nem_sessao_poluida(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    term_id = await make_term(app_session_factory, tenant_id)
    redis: Redis = create_redis_client()
    try:

        def failing_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"message": "erro"})

        def empty_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"count": 0, "items": []})

        source = _djen_source(httpx.MockTransport(failing_handler))
        async with app_session_factory() as session:
            await set_tenant_context(session, tenant_id)
            service = TermSyncService(session, tenant_id, source, lock=RedisSyncLock(redis))
            term = await session.get(MonitoredTerm, term_id)
            assert term is not None
            run = await service.sync_term(term)
            assert run is not None and run.error is not None

            # O lock some junto — outra chamada consegue adquirir na hora, sem esperar TTL.
            reacquired = await RedisSyncLock(redis).acquire(
                f"rito:djen_sync:{term_id}", ttl_seconds=5
            )
            assert reacquired is True
            await RedisSyncLock(redis).release(f"rito:djen_sync:{term_id}")

            # A MESMA sessão continua utilizável depois do rollback — prova que a falha
            # não deixou a transação num estado poluído (spec 049 precisou de um
            # session.refresh() explícito exatamente por causa disso).
            recovery_source = _djen_source(httpx.MockTransport(empty_handler))
            service2 = TermSyncService(session, tenant_id, recovery_source)
            term = await session.get(MonitoredTerm, term_id)
            assert term is not None
            recovered = await service2.sync_term(term)
            assert recovered is not None and recovered.error is None
    finally:
        await redis.aclose()


# ---- Auditoria §5 (cobertura): isolamento de tenant em lawsuit_subjects -------------


async def test_rls_lawsuit_subjects_isola_por_tenant(
    setup: SyncSetup, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """`lawsuit_subjects` (tabela nova da spec 047) tinha RLS habilitado na
    migration mas nenhum teste provando isolamento — gap achado na auditoria
    §5 da 050 (CLAUDE.md §4: toda tabela nova exige esse teste)."""
    lawsuit_a = await setup.create_lawsuit(process_number=_cnj(970))
    async with setup.sessions() as session, session.begin():
        await set_tenant_context(session, setup.gestor.tenant_id)
        session.add(
            LawsuitSubject(
                tenant_id=setup.gestor.tenant_id, lawsuit_id=lawsuit_a, code=7768, name="Rescisão"
            )
        )

    gestor_b = await make_user(role=UserRole.GESTOR)
    headers_b = _auth_header(gestor_b)
    type_id_b, _group_id_b = await _create_lawsuit_type(setup.client, headers_b)
    stage_id_b = await _create_stage(setup.client, headers_b)
    lawsuit_b = await _create_lawsuit(
        setup.client,
        headers_b,
        user_id=str(gestor_b.user_id),
        lawsuit_type_id=type_id_b,
        stage_id=stage_id_b,
    )
    lawsuit_b_id = uuid.UUID(str(lawsuit_b["id"]))
    async with setup.sessions() as session, session.begin():
        await set_tenant_context(session, gestor_b.tenant_id)
        session.add(
            LawsuitSubject(
                tenant_id=gestor_b.tenant_id, lawsuit_id=lawsuit_b_id, code=1127, name="Cobrança"
            )
        )

    async with setup.sessions() as session:
        await set_tenant_context(session, setup.gestor.tenant_id)
        visible_to_a = (await session.scalars(select(LawsuitSubject))).all()
        assert {row.code for row in visible_to_a} == {7768}  # não enxerga o de B

    async with setup.sessions() as session:
        await set_tenant_context(session, gestor_b.tenant_id)
        visible_to_b = (await session.scalars(select(LawsuitSubject))).all()
        assert {row.code for row in visible_to_b} == {1127}  # não enxerga o de A


# ---- Auditoria §5 (banco): retenção de 90 dias de sync_runs de verdade -------------


async def test_purge_older_than_apaga_so_o_que_venceu(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    """Regra 9 da 049: `TermSyncRunRepository.purge_older_than` — a `sync_runs`
    unificada (spec 050) precisa que a retenção funcione dos dois lados; DJEN já
    tinha o método (049) mas nenhum teste provava o comportamento (gap achado
    na auditoria §5 — `_purge` de `external_requests`, spec 041, é
    deliberadamente não testado por design, documentado no próprio módulo;
    este repositório é tenant-scoped e segue o padrão normal de teste)."""
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    term_id = await make_term(app_session_factory, tenant_id)
    cutoff = datetime.now(UTC) - timedelta(days=90)

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        session.add_all(
            [
                TermSyncRun(
                    tenant_id=tenant_id,
                    term_id=term_id,
                    started_at=cutoff - timedelta(days=1),  # vencida
                ),
                TermSyncRun(
                    tenant_id=tenant_id,
                    term_id=term_id,
                    started_at=cutoff + timedelta(days=1),  # dentro da janela
                ),
            ]
        )

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        deleted = await TermSyncRunRepository(session).purge_older_than(cutoff)
        assert deleted == 1

    async with app_session_factory() as session:
        await set_tenant_context(session, tenant_id)
        remaining = (
            await session.scalars(select(TermSyncRun).where(TermSyncRun.term_id == term_id))
        ).all()
        assert len(remaining) == 1
        assert remaining[0].started_at >= cutoff
