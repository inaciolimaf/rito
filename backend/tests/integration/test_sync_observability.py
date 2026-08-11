"""Observabilidade da sincronização (spec 049, §8).

Falha vira ALERTA (`integration_alerts`), não tarefa: `posts.lawsuit_id` é
NOT NULL desde a spec 032 e um alerta de sincronização não tem processo — a
decisão está registrada nas Descobertas da 049.

Alertas de SISTEMA (`tenant_id=None`) e `integration_health` (sem tenant_id
algum) nunca são commitados aqui — o mesmo cuidado do teste de 401 da spec 046
(`test_datajud_service.py`): sem transação global de rollback entre testes,
commitar uma linha visível a QUALQUER tenant vazaria pros demais testes do
processo.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.integration_alerts.models import IntegrationAlert
from app.domain.integration_alerts.repository import IntegrationAlertRepository
from app.domain.integrations.models import IntegrationHealth
from app.domain.integrations.service import (
    HealthCheckResult,
    IntegrationHealthService,
    IntegrationStatusService,
)
from app.domain.monitored_terms.models import MonitoredTerm, TermKind, TermStatus
from app.domain.publications.metrics import PublicationMetricsService
from app.domain.publications.models import Publication
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser
from tests.integration.test_djen_sync import FakeSource, make_term, run_sync
from tests.integration.test_lawsuits import _auth_header

SessionFactory = async_sessionmaker[AsyncSession]


class FakeChecker:
    def __init__(self, integration: str, result: HealthCheckResult) -> None:
        self.integration = integration
        self._result = result

    async def check(self) -> HealthCheckResult:
        return self._result


def _make_publication(
    tenant_id: uuid.UUID, *, seq: int, matched_by: str | None, availability_date: date
) -> Publication:
    return Publication(
        tenant_id=tenant_id,
        external_id=seq,
        hash=f"metrics-test-{seq}",
        availability_date=availability_date,
        court_code="TJSP",
        body="Texto de teste.",
        raw_payload={},
        matched_by=matched_by,
        processed_at=datetime.now(UTC),
    )


async def _fetch_alert_state(
    factory: SessionFactory, tenant_id: uuid.UUID, term_id: uuid.UUID
) -> tuple[int, uuid.UUID | None]:
    async with factory() as session:
        await set_tenant_context(session, tenant_id)
        term = await session.get(MonitoredTerm, term_id)
        assert term is not None
        return term.consecutive_failures, term.alert_id


async def _fetch_alert(
    factory: SessionFactory, tenant_id: uuid.UUID, alert_id: uuid.UUID
) -> IntegrationAlert:
    async with factory() as session:
        await set_tenant_context(session, tenant_id)
        alert = await session.get(IntegrationAlert, alert_id)
        assert alert is not None
        return alert


async def test_tres_falhas_criam_alerta_de_aviso(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    """Regra 1: sem responsável no termo, o alerta cai pro GESTOR mais antigo
    (mesma cascata de fallback da 045)."""
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    term_id = await make_term(app_session_factory, tenant_id)
    source = FakeSource()
    source.queue_error("timeout 1")
    source.queue_error("timeout 2")
    source.queue_error("timeout 3")

    for _ in range(3):
        await run_sync(app_session_factory, tenant_id, term_id, source)

    failures, alert_id = await _fetch_alert_state(app_session_factory, tenant_id, term_id)
    assert failures == 3
    assert alert_id is not None
    alert = await _fetch_alert(app_session_factory, tenant_id, alert_id)
    assert alert.severity == "warning"
    assert alert.code == "term_sync_failed"
    assert alert.integration == "djen"
    assert alert.responsible_user_id == gestor.user_id
    assert alert.resolved_at is None


async def test_quarta_falha_atualiza_mensagem_sem_duplicar(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    """Regra 2: um alerta só por termo — a 4ª falha atualiza a mensagem."""
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    term_id = await make_term(app_session_factory, tenant_id)
    source = FakeSource()
    for message in ("erro 1", "erro 2", "erro 3", "erro 4"):
        source.queue_error(message)
    for _ in range(4):
        await run_sync(app_session_factory, tenant_id, term_id, source)

    failures, alert_id = await _fetch_alert_state(app_session_factory, tenant_id, term_id)
    assert failures == 4
    assert alert_id is not None

    async with app_session_factory() as session:
        await set_tenant_context(session, tenant_id)
        total = await session.scalar(select(func.count()).select_from(IntegrationAlert))
    assert total == 1

    alert = await _fetch_alert(app_session_factory, tenant_id, alert_id)
    assert "erro 4" in alert.message  # a 4ª falha foi anexada
    assert "erro 3" in alert.message  # a mensagem original (limiar da 3ª) não foi substituída


async def test_sucesso_apos_falha_zera_contador_e_resolve_alerta(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    """Regra 3: sucesso zera `consecutive_failures`, resolve o alerta e limpa
    `monitored_terms.alert_id`."""
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    term_id = await make_term(app_session_factory, tenant_id)
    source = FakeSource()
    source.queue_error("falha 1")
    source.queue_error("falha 2")
    source.queue_error("falha 3")
    for _ in range(3):
        await run_sync(app_session_factory, tenant_id, term_id, source)
    failures, alert_id = await _fetch_alert_state(app_session_factory, tenant_id, term_id)
    assert failures == 3 and alert_id is not None

    source.queue_page([])
    await run_sync(app_session_factory, tenant_id, term_id, source)

    failures, cleared_alert_id = await _fetch_alert_state(app_session_factory, tenant_id, term_id)
    assert failures == 0
    assert cleared_alert_id is None
    resolved = await _fetch_alert(app_session_factory, tenant_id, alert_id)
    assert resolved.resolved_at is not None


async def test_sucesso_anexa_nota_de_normalizacao(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    term_id = await make_term(app_session_factory, tenant_id)
    source = FakeSource()
    source.queue_error("falha")
    source.queue_error("falha")
    source.queue_error("falha")
    for _ in range(3):
        await run_sync(app_session_factory, tenant_id, term_id, source)
    _, alert_id = await _fetch_alert_state(app_session_factory, tenant_id, term_id)
    assert alert_id is not None

    source.queue_page([])
    await run_sync(app_session_factory, tenant_id, term_id, source)

    resolved = await _fetch_alert(app_session_factory, tenant_id, alert_id)
    assert "Normalizado" in resolved.message


async def test_401_datajud_aparece_como_alerta_critico(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    """Regra 4: o alerta crítico da spec 046 (401 do DataJud) aparece no mesmo
    painel de observabilidade — `list_filtered(resolved=False)` da 049."""
    gestor = await make_user(role=UserRole.GESTOR)
    async with app_session_factory() as session:
        await set_tenant_context(session, gestor.tenant_id)
        alerts = IntegrationAlertRepository(session)
        await alerts.create(
            IntegrationAlert(
                tenant_id=None,
                integration="datajud",
                severity="critical",
                code="api_key_rotated",
                message="A chave pública do DataJud foi rotacionada.",
            )
        )
        open_alerts = await alerts.list_filtered(resolved=False)
        assert any(a.severity == "critical" and a.integration == "datajud" for a in open_alerts)


async def test_job_de_saude_grava_latencia(app_session_factory: SessionFactory) -> None:
    async with app_session_factory() as session:
        service = IntegrationHealthService(session)
        checker = FakeChecker(
            "djen", HealthCheckResult(is_healthy=True, latency_ms=42, detail=None)
        )
        record = await service.run_check(checker)

        assert record.integration == "djen"
        assert record.is_healthy is True
        assert record.latency_ms == 42
        rows = (await session.scalars(select(IntegrationHealth))).all()
        assert len(rows) == 1


async def test_duas_saudes_falhas_seguidas_criam_alerta_critico(
    app_session_factory: SessionFactory,
) -> None:
    async with app_session_factory() as session:
        service = IntegrationHealthService(session)
        unhealthy = HealthCheckResult(is_healthy=False, latency_ms=None, detail="timeout")

        await service.run_check(FakeChecker("datajud", unhealthy))
        assert (await session.scalars(select(IntegrationAlert))).all() == []  # 1ª não basta

        await service.run_check(FakeChecker("datajud", unhealthy))
        alert = (await session.scalars(select(IntegrationAlert))).one()
        assert alert.severity == "critical"
        assert alert.code == "health_check_failed"
        assert alert.integration == "datajud"

        await service.run_check(FakeChecker("datajud", unhealthy))  # dedup: não duplica
        assert len((await session.scalars(select(IntegrationAlert))).all()) == 1


async def test_taxa_de_vinculo_abaixo_de_70_gera_aviso(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    today = date.today()
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        for seq in range(6):
            session.add(
                _make_publication(
                    tenant_id, seq=seq, matched_by="process_number", availability_date=today
                )
            )
        for seq in range(6, 10):
            session.add(
                _make_publication(tenant_id, seq=seq, matched_by=None, availability_date=today)
            )

    async with app_session_factory() as session:
        await set_tenant_context(session, tenant_id)
        service = PublicationMetricsService(session, tenant_id)
        metrics = await service.get_metrics(period_days=7, today=today)
        assert metrics.total == 10
        assert metrics.auto_linked == 6
        assert metrics.auto_link_rate == pytest.approx(0.6)

        alert = await service.check_auto_link_rate()
        assert alert is not None
        assert alert.code == "low_auto_link_rate"
        assert alert.severity == "warning"
        assert alert.tenant_id == tenant_id

        again = await service.check_auto_link_rate()
        assert again is None  # regra de dedup: já tem um aberto


async def test_status_agrega_termos_por_status(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        session.add_all(
            [
                MonitoredTerm(
                    tenant_id=tenant_id,
                    kind=TermKind.OAB,
                    value="111111",
                    oab_state="SP",
                    status=TermStatus.ATIVO,
                ),
                MonitoredTerm(
                    tenant_id=tenant_id,
                    kind=TermKind.OAB,
                    value="222222",
                    oab_state="SP",
                    status=TermStatus.ATIVO,
                ),
                MonitoredTerm(
                    tenant_id=tenant_id,
                    kind=TermKind.OAB,
                    value="333333",
                    oab_state="SP",
                    status=TermStatus.FALHA,
                ),
                MonitoredTerm(
                    tenant_id=tenant_id,
                    kind=TermKind.OAB,
                    value="444444",
                    oab_state="SP",
                    status=TermStatus.PAUSADO,
                ),
            ]
        )

    async with app_session_factory() as session:
        await set_tenant_context(session, tenant_id)
        status = await IntegrationStatusService(session).get_status()

    counts = {item.status: item.count for item in status.terms_by_status}
    assert counts[TermStatus.ATIVO] == 2
    assert counts[TermStatus.FALHA] == 1
    assert counts[TermStatus.PAUSADO] == 1
    assert {item.integration for item in status.integrations} == {"djen", "datajud"}


async def test_colaborador_recebe_403(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador = await make_user(role=UserRole.COLABORADOR)
    response = await client.get("/api/v1/integrations/status", headers=_auth_header(colaborador))
    assert response.status_code == 403
