"""BI: camada de agregação (spec 078).

A fila nunca participa de teste (CLAUDE.md §3): os testes chamam `refresh_aggregate`
e `refresh_due_aggregates` direto com a MIGRATIONS_DATABASE_URL de teste, e
`schedule_aggregate_refresh` é no-op proposital em APP_ENV=test. O estado do
registry é GLOBAL (sem tenant), então cada teste fixa explicitamente o
`last_refresh_at` de que depende — runs no mesmo worker compartilham o banco.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import TypedDict

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

import app.workers.aggregates as aggregates_worker
from app.core.config import get_settings
from app.core.materialized_view import MATERIALIZED_VIEWS
from app.domain.users.models import FinancialAccess, UserRole
from app.workers.aggregates import (
    EVENT_TO_VIEWS,
    refresh_aggregate,
    refresh_due_aggregates,
    schedule_aggregate_refresh,
)
from tests.integration.conftest import SeededUser, auth_header

_SPEC_EVENTS = {"lawsuit.closed", "transaction.paid", "task.completed", "lawsuit.archived"}

# (view, intervalo em segundos) — regra 2: BI 8 h, produtividade/agilidade 15 min,
# saldo diário 10 min.
_EXPECTED_INTERVALS = {
    "user_monthly_scores": 900,
    "account_daily_balances": 600,
    "agility_daily": 900,
    "timesheet_daily": 900,
    "bi_pipeline_monthly": 28800,
    "bi_vintage": 28800,
    "bi_lawsuit_cycles": 28800,
    "bi_cost_allocation": 28800,
}


def _migrations_url() -> str:
    url = get_settings().migrations_database_url
    assert url is not None
    return url


async def _set_registry_state(
    admin_engine: AsyncEngine,
    name: str,
    *,
    last_refresh_at: datetime | None,
    last_error: str | None = None,
) -> None:
    async with admin_engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE aggregate_registry SET last_refresh_at = :at, last_error = :error "
                "WHERE name = :name"
            ),
            {"at": last_refresh_at, "error": last_error, "name": name},
        )


class _RegistryState(TypedDict):
    last_refresh_at: datetime | None
    last_refresh_duration_ms: int | None
    last_error: str | None


async def _registry_row(admin_engine: AsyncEngine, name: str) -> _RegistryState:
    async with admin_engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT last_refresh_at, last_refresh_duration_ms, last_error "
                    "FROM aggregate_registry WHERE name = :name"
                ),
                {"name": name},
            )
        ).one()
    return {
        "last_refresh_at": row.last_refresh_at,
        "last_refresh_duration_ms": row.last_refresh_duration_ms,
        "last_error": row.last_error,
    }


async def test_status_lista_agregados_com_intervalos_e_exige_administrador(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    colaborador = await make_user(role=UserRole.COLABORADOR)
    administrador = await make_user(role=UserRole.ADMINISTRADOR)

    forbidden = await client.get("/api/v1/aggregates/status", headers=auth_header(colaborador))
    assert forbidden.status_code == 403

    response = await client.get("/api/v1/aggregates/status", headers=auth_header(administrador))
    assert response.status_code == 200, response.json()
    items = {item["name"]: item for item in response.json()["items"]}
    assert set(items) == {spec.view_name for spec in MATERIALIZED_VIEWS}
    for name, interval in _EXPECTED_INTERVALS.items():
        assert items[name]["refresh_interval_seconds"] == interval
        assert items[name]["is_enabled"] is True
        assert isinstance(items[name]["is_stale"], bool)


async def test_refresh_concorrente_nao_bloqueia_leitura(admin_engine: AsyncEngine) -> None:
    """Regra 3: REFRESH CONCURRENTLY — leituras na view seguem respondendo durante
    o refresh (sem lock exclusivo)."""
    url = _migrations_url()

    async def _read_repeatedly() -> list[int]:
        counts: list[int] = []
        async with admin_engine.connect() as conn:
            for _ in range(5):
                result = await conn.execute(text("SELECT count(*) FROM user_monthly_scores"))
                counts.append(result.scalar_one())
        return counts

    outcome, counts = await asyncio.gather(
        refresh_aggregate("user_monthly_scores", url), _read_repeatedly()
    )
    assert outcome.name == "user_monthly_scores"
    assert len(counts) == 5  # nenhuma leitura bloqueou ou falhou durante o refresh

    row = await _registry_row(admin_engine, "user_monthly_scores")
    assert row["last_refresh_at"] is not None
    assert row["last_error"] is None


async def test_evento_agenda_refresh_sem_bloquear_operacao(admin_engine: AsyncEngine) -> None:
    """Regras 4 e 5: agendar é síncrono, sem I/O e sem exceção mesmo com o broker
    fora (no-op em APP_ENV=test) — a operação de domínio nunca espera a fila. E o
    mapeamento evento → views bate com o `invalidate_on` semeado no registry."""
    assert set(EVENT_TO_VIEWS) == _SPEC_EVENTS
    known = {spec.view_name for spec in MATERIALIZED_VIEWS}
    for event, views in EVENT_TO_VIEWS.items():
        assert set(views) <= known
        schedule_aggregate_refresh(event)  # não levanta, não toca rede
    schedule_aggregate_refresh("evento.desconhecido")  # evento fora da regra 5: no-op

    # EVENT_TO_VIEWS e o invalidate_on do seed (migration 078) contam a mesma história.
    async with admin_engine.connect() as conn:
        rows = (
            await conn.execute(text("SELECT name, invalidate_on FROM aggregate_registry"))
        ).all()
    invalidate_on = {row.name: set(row.invalidate_on) for row in rows}
    for event, views in EVENT_TO_VIEWS.items():
        for view in views:
            assert event in invalidate_on[view], f"{event} ausente em invalidate_on de {view}"


async def test_is_stale_a_partir_de_duas_vezes_o_intervalo(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    admin_engine: AsyncEngine,
) -> None:
    """Regra 6: is_stale só quando a defasagem passa de 2× o intervalo (900 s →
    estoura em 1800 s)."""
    now = datetime.now(UTC)
    await _set_registry_state(
        admin_engine, "user_monthly_scores", last_refresh_at=now - timedelta(seconds=1801)
    )
    await _set_registry_state(
        admin_engine, "account_daily_balances", last_refresh_at=now - timedelta(seconds=600)
    )
    administrador = await make_user(role=UserRole.ADMINISTRADOR)

    response = await client.get("/api/v1/aggregates/status", headers=auth_header(administrador))
    assert response.status_code == 200, response.json()
    items = {item["name"]: item for item in response.json()["items"]}

    stale = items["user_monthly_scores"]
    assert stale["is_stale"] is True
    assert stale["staleness_seconds"] >= 1801
    fresh = items["account_daily_balances"]
    assert fresh["is_stale"] is False
    assert fresh["staleness_seconds"] >= 600


async def test_falha_no_refresh_serve_dado_antigo_com_aviso(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    admin_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regra 7: refresh quebrado registra o erro, preserva o último dado bom e a
    resposta de BI continua 200 — com meta sinalizando a defasagem, nunca erro."""
    old_refresh = datetime.now(UTC) - timedelta(hours=30)  # além de 2× o intervalo de 8 h
    await _set_registry_state(admin_engine, "bi_vintage", last_refresh_at=old_refresh)

    async def _broken(conn: object, name: str) -> None:
        raise RuntimeError("view travada para o teste")

    monkeypatch.setattr(aggregates_worker, "_refresh_view", _broken)
    with pytest.raises(RuntimeError, match="view travada"):
        await refresh_aggregate("bi_vintage", _migrations_url())

    row = await _registry_row(admin_engine, "bi_vintage")
    assert row["last_error"] is not None and "view travada" in str(row["last_error"])
    last_refresh = row["last_refresh_at"]
    assert last_refresh is not None
    # O timestamp do dado antigo é preservado — só o erro muda.
    assert abs((last_refresh - old_refresh).total_seconds()) < 1
    async with admin_engine.connect() as conn:
        logged = (
            await conn.execute(
                text(
                    "SELECT error FROM aggregate_refresh_log "
                    "WHERE name = 'bi_vintage' ORDER BY started_at DESC LIMIT 1"
                )
            )
        ).scalar_one()
    assert "view travada" in logged

    gestor = await make_user(role=UserRole.GESTOR)
    response = await client.get("/api/v1/bi/vintage", headers=auth_header(gestor))
    assert response.status_code == 200, response.json()  # dado velho, nunca erro
    meta = response.json()["meta"]
    assert meta["is_stale"] is True
    assert meta["staleness_seconds"] >= 30 * 3600


async def test_refresh_manual_throttle_um_a_cada_10_min(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Regra 8: 1 refresh manual por agregado a cada 10 min por tenant — o segundo
    vira 429. Rota exige GESTOR; nome desconhecido vira 404 antes do throttle."""
    gestor = await make_user(role=UserRole.GESTOR)
    headers = auth_header(gestor)

    not_found = await client.post("/api/v1/aggregates/view_que_nao_existe/refresh", headers=headers)
    assert not_found.status_code == 404

    first = await client.post("/api/v1/aggregates/user_monthly_scores/refresh", headers=headers)
    assert first.status_code == 200, first.json()
    assert first.json()["name"] == "user_monthly_scores"
    assert first.json()["last_refresh_at"] is not None

    second = await client.post("/api/v1/aggregates/user_monthly_scores/refresh", headers=headers)
    assert second.status_code == 429

    # O throttle é por tenant: outro tenant ainda consegue.
    outro_gestor = await make_user(role=UserRole.GESTOR)
    other_tenant = await client.post(
        "/api/v1/aggregates/user_monthly_scores/refresh", headers=auth_header(outro_gestor)
    )
    assert other_tenant.status_code == 200

    colaborador = await make_user(role=UserRole.COLABORADOR)
    forbidden = await client.post(
        "/api/v1/aggregates/user_monthly_scores/refresh", headers=auth_header(colaborador)
    )
    assert forbidden.status_code == 403


async def test_refresh_lento_gera_alerta(
    admin_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regra 9: refresh acima de 60 s gera alerta de sistema em integration_alerts
    (sem sleep — o relógio do worker é simulado)."""
    ticks = iter([1_000.0, 1_061.0])  # 61 s de refresh simulado
    monkeypatch.setattr(aggregates_worker, "monotonic", lambda: next(ticks))
    try:
        outcome = await refresh_aggregate("agility_daily", _migrations_url())
        assert outcome.duration_ms == 61_000

        async with admin_engine.connect() as conn:
            alert = (
                await conn.execute(
                    text(
                        "SELECT severity, code, message, tenant_id FROM integration_alerts "
                        "WHERE integration = 'aggregates' AND code = 'slow_refresh'"
                    )
                )
            ).one()
        assert alert.severity == "warning"
        assert alert.tenant_id is None  # alerta de sistema, não de um tenant
        assert alert.message.startswith("agility_daily:")
    finally:
        async with admin_engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM integration_alerts WHERE integration = 'aggregates'")
            )


async def test_falha_em_um_agregado_nao_impede_os_outros(
    admin_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regra 11: o orquestrador segue sequencial (regra 10) mesmo quando uma view
    falha — a falhada fica com last_error, as demais atualizam normalmente."""
    now = datetime.now(UTC)
    async with admin_engine.begin() as conn:
        # Tudo fresco (nada vencido) exceto as duas views alvo do teste.
        await conn.execute(
            text("UPDATE aggregate_registry SET last_refresh_at = :now"), {"now": now}
        )
        await conn.execute(
            text(
                "UPDATE aggregate_registry SET last_refresh_at = NULL "
                "WHERE name IN ('agility_daily', 'timesheet_daily')"
            )
        )

    async def _broken_for_agility(conn: AsyncConnection, name: str) -> None:
        if name == "agility_daily":
            raise RuntimeError("falha simulada")
        await conn.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {name}"))

    monkeypatch.setattr(aggregates_worker, "_refresh_view", _broken_for_agility)
    refreshed = await refresh_due_aggregates(_migrations_url())

    assert refreshed == ["timesheet_daily"]  # agility falhou, timesheet refrescou
    broken = await _registry_row(admin_engine, "agility_daily")
    assert broken["last_error"] is not None and "falha simulada" in str(broken["last_error"])
    assert broken["last_refresh_at"] is None  # dado antigo (nulo) preservado
    ok = await _registry_row(admin_engine, "timesheet_daily")
    assert ok["last_refresh_at"] is not None
    assert ok["last_error"] is None


async def test_meta_em_toda_resposta_de_bi(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """§5: toda resposta de BI carrega `meta` com computed_at, staleness_seconds e
    is_stale — da view (quando atrelada a uma) ou de tempo real (defasagem zero)."""
    await refresh_aggregate("bi_pipeline_monthly", _migrations_url())
    gestor = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    headers = auth_header(gestor)

    view_backed = await client.get("/api/v1/bi/pipeline", headers=headers)
    assert view_backed.status_code == 200, view_backed.json()
    meta = view_backed.json()["meta"]
    assert meta["computed_at"] is not None
    assert meta["staleness_seconds"] >= 0
    assert meta["is_stale"] is False

    # Views nunca refrescadas pelo orquestrador reportam computed_at nulo (regra 6:
    # sem timestamp, conta como defasado) — mas a resposta continua 200.
    for path in ("/api/v1/bi/vintage", "/api/v1/bi/time-fees", "/api/v1/bi/costs"):
        response = await client.get(path, headers=headers)
        assert response.status_code == 200, response.json()
        body_meta = response.json()["meta"]
        assert set(body_meta) == {"computed_at", "staleness_seconds", "is_stale"}

    # Endpoint de tempo real: defasagem zero por construção.
    realtime = await client.get("/api/v1/bi/pipeline/portfolio", headers=headers)
    assert realtime.status_code == 200, realtime.json()
    realtime_meta_body = realtime.json()["meta"]
    assert realtime_meta_body["staleness_seconds"] == 0
    assert realtime_meta_body["is_stale"] is False


async def test_expurgo_do_log_de_refresh_respeita_a_retencao(admin_engine: AsyncEngine) -> None:
    """Refatoração 080: `aggregate_refresh_log` era a única tabela sem teto de
    crescimento (uma linha por view por minuto). O expurgo apaga o que passou de 90
    dias e não encosta no recente."""
    from app.workers.aggregates import REFRESH_LOG_RETENTION_DAYS, purge_refresh_log

    url = get_settings().migrations_database_url
    assert url is not None

    async with admin_engine.begin() as conn:
        antigo = (
            await conn.execute(
                text(
                    "INSERT INTO aggregate_refresh_log (name, started_at) "
                    "VALUES ('bi_vintage', now() - make_interval(days => :days)) RETURNING id"
                ),
                {"days": REFRESH_LOG_RETENTION_DAYS + 1},
            )
        ).scalar_one()
        recente = (
            await conn.execute(
                text(
                    "INSERT INTO aggregate_refresh_log (name, started_at) "
                    "VALUES ('bi_vintage', now()) RETURNING id"
                )
            )
        ).scalar_one()

    await purge_refresh_log(url)

    async with admin_engine.begin() as conn:
        sobreviventes = (
            (
                await conn.execute(
                    text("SELECT id FROM aggregate_refresh_log WHERE id IN (:a, :b)"),
                    {"a": antigo, "b": recente},
                )
            )
            .scalars()
            .all()
        )

    assert sobreviventes == [recente]
