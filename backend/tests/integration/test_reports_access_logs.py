"""Registro de acessos e livro de ponto (spec 073).

`timesheet_daily` é estática entre refreshes (mesmo padrão de 039/071): os testes
inserem `access_logs` direto (quando a API não dá controle sobre `occurred_at`) e
chamam `refresh_timesheet_daily` direto, sem fila (CLAUDE.md §3).
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.rls import set_tenant_context
from app.domain.reports.models import AccessLog
from app.domain.users.models import UserRole
from app.domain.workflows.models import Holiday
from app.workers.timesheet import _purge_tenant, refresh_timesheet_daily
from tests.integration.conftest import SeededUser, auth_header
from tests.integration.test_account import _valid_payload
from tests.integration.test_lawsuits_listing import LawsuitFactory, _make_factory

_TODAY = datetime.now(UTC).date()
_MONTH_START = _TODAY.replace(day=1)


@pytest.fixture
async def factory(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> LawsuitFactory:
    return await _make_factory(client, make_user, app_session_factory)


async def _create_account(client: AsyncClient, headers: dict[str, str]) -> None:
    response = await client.put("/api/v1/account", json=_valid_payload(), headers=headers)
    assert response.status_code == 200, response.json()


async def _set_tracking(client: AsyncClient, headers: dict[str, str], enabled: bool) -> None:
    response = await client.put(
        "/api/v1/account/access-tracking", json={"enabled": enabled}, headers=headers
    )
    assert response.status_code == 200, response.json()


async def _seed_access_log(
    app_session_factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    occurred_at: datetime,
) -> None:
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        session.add(
            AccessLog(
                tenant_id=tenant_id,
                user_id=user_id,
                occurred_at=occurred_at,
                ip_address="203.0.113.5",
            )
        )


async def _seed_holiday(
    app_session_factory: async_sessionmaker[AsyncSession], day: date, name: str
) -> None:
    # holidays é tabela global sem tenant_id — não é limpa entre execuções da suíte
    # (spec 009 regra 3, TRUNCATE tenants CASCADE só atinge tabelas de tenant), então
    # reruns locais podem achar a mesma data já semeada por uma execução anterior.
    async with app_session_factory() as session, session.begin():
        existing = await session.get(Holiday, day)
        if existing is None:
            session.add(Holiday(id=day, name=name, is_national=True))
        else:
            existing.is_national = True


async def _refresh() -> None:
    url = get_settings().migrations_database_url
    assert url is not None
    await refresh_timesheet_daily(url)


async def _timesheet(
    client: AsyncClient, headers: dict[str, str], *, user_id: str | None = None
) -> Any:
    params: dict[str, str] = {"month": f"{_MONTH_START:%Y-%m}"}
    if user_id:
        params["user_id"] = user_id
    response = await client.get("/api/v1/reports/timesheet", params=params, headers=headers)
    assert response.status_code == 200, response.json()
    return response.json()


async def _set_work_hours(
    client: AsyncClient, headers: dict[str, str], user_id: str, *, start: str, end: str
) -> None:
    response = await client.put(
        f"/api/v1/users/{user_id}",
        json={
            "name": "Colaborador Jornada",
            "role": "COLABORADOR",
            "financial_access": "NONE",
            "work_start": start,
            "work_end": end,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.json()


async def test_desligado_nao_registra(client: AsyncClient, factory: LawsuitFactory) -> None:
    await _create_account(client, factory.headers)
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": factory.gestor.email, "password": factory.gestor.password},
        headers={"X-Tenant-Id": str(factory.gestor.tenant_id)},
    )
    assert login.status_code == 200

    response = await client.get("/api/v1/reports/access-logs", headers=factory.headers)
    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_ligado_registra_no_login_nao_no_refresh(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    await _create_account(client, factory.headers)
    await _set_tracking(client, factory.headers, True)

    tenant_headers = {"X-Tenant-Id": str(factory.gestor.tenant_id)}
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": factory.gestor.email, "password": factory.gestor.password},
        headers=tenant_headers,
    )
    assert login.status_code == 200
    login_body = login.json()

    logs_after_login = await client.get("/api/v1/reports/access-logs", headers=factory.headers)
    assert logs_after_login.json()["total"] == 1

    refresh = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login_body["refresh_token"]},
        headers=tenant_headers,
    )
    assert refresh.status_code == 200

    logs_after_refresh = await client.get("/api/v1/reports/access-logs", headers=factory.headers)
    assert logs_after_refresh.json()["total"] == 1


@pytest.mark.commits
async def test_primeiro_e_ultimo_acesso_do_dia(
    client: AsyncClient,
    factory: LawsuitFactory,
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _create_account(client, factory.headers)
    day = _MONTH_START
    morning = datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=12)
    evening = morning + timedelta(hours=5)
    await _seed_access_log(
        app_session_factory, factory.gestor.tenant_id, factory.gestor.user_id, morning
    )
    await _seed_access_log(
        app_session_factory, factory.gestor.tenant_id, factory.gestor.user_id, evening
    )
    await _refresh()

    body = await _timesheet(client, factory.headers, user_id=str(factory.gestor.user_id))
    cell = next(d for d in body["days"] if d["day"] == day.isoformat())
    assert cell["access_count"] == 2
    assert cell["first_access"] is not None
    assert cell["last_access"] is not None
    assert cell["first_access"] < cell["last_access"]


@pytest.mark.commits
async def test_desvio_positivo_e_negativo(
    client: AsyncClient,
    factory: LawsuitFactory,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _create_account(client, factory.headers)
    colaborador = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    await _set_work_hours(
        client, factory.headers, str(colaborador.user_id), start="09:00:00", end="18:00:00"
    )

    late_day = _MONTH_START
    early_day = _MONTH_START + timedelta(days=1)
    # America/Sao_Paulo = UTC-3 (sem horário de verão desde 2019).
    late_utc = datetime.combine(late_day, datetime.min.time(), tzinfo=UTC) + timedelta(
        hours=12, minutes=30
    )
    early_utc = datetime.combine(early_day, datetime.min.time(), tzinfo=UTC) + timedelta(
        hours=11, minutes=45
    )
    await _seed_access_log(
        app_session_factory, factory.gestor.tenant_id, colaborador.user_id, late_utc
    )
    await _seed_access_log(
        app_session_factory, factory.gestor.tenant_id, colaborador.user_id, early_utc
    )
    await _refresh()

    body = await _timesheet(client, factory.headers, user_id=str(colaborador.user_id))
    late_cell = next(d for d in body["days"] if d["day"] == late_day.isoformat())
    early_cell = next(d for d in body["days"] if d["day"] == early_day.isoformat())
    assert late_cell["deviation_minutes"] == 30
    assert early_cell["deviation_minutes"] == -15


@pytest.mark.commits
async def test_sem_jornada_sem_comparacao(
    client: AsyncClient,
    factory: LawsuitFactory,
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _create_account(client, factory.headers)
    day = _MONTH_START
    moment = datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=12)
    await _seed_access_log(
        app_session_factory, factory.gestor.tenant_id, factory.gestor.user_id, moment
    )
    await _refresh()

    body = await _timesheet(client, factory.headers, user_id=str(factory.gestor.user_id))
    cell = next(d for d in body["days"] if d["day"] == day.isoformat())
    assert cell["access_count"] == 1
    assert cell["deviation_minutes"] is None


async def test_dia_sem_acesso_fica_vazio(client: AsyncClient, factory: LawsuitFactory) -> None:
    await _create_account(client, factory.headers)
    body = await _timesheet(client, factory.headers, user_id=str(factory.gestor.user_id))
    cell = next(d for d in body["days"] if d["day"] == _MONTH_START.isoformat())
    assert cell["access_count"] == 0
    assert cell["first_access"] is None
    assert cell["last_access"] is None
    assert cell["deviation_minutes"] is None


async def test_fim_de_semana_e_feriado_marcados(
    client: AsyncClient,
    factory: LawsuitFactory,
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _create_account(client, factory.headers)
    saturday = next(
        _MONTH_START + timedelta(days=offset)
        for offset in range(7)
        if (_MONTH_START + timedelta(days=offset)).weekday() == 5
    )
    holiday_day = _MONTH_START + timedelta(days=2)
    await _seed_holiday(app_session_factory, holiday_day, "Feriado de teste")

    body = await _timesheet(client, factory.headers, user_id=str(factory.gestor.user_id))
    saturday_cell = next(d for d in body["days"] if d["day"] == saturday.isoformat())
    holiday_cell = next(d for d in body["days"] if d["day"] == holiday_day.isoformat())
    assert saturday_cell["is_weekend"] is True
    assert holiday_cell["is_holiday"] is True


async def test_proprio_ve_alheio_nao_admin_ve(
    client: AsyncClient, factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    await _create_account(client, factory.headers)
    colaborador = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    headers = auth_header(colaborador)

    own = await client.get(
        "/api/v1/reports/timesheet", params={"month": f"{_MONTH_START:%Y-%m}"}, headers=headers
    )
    assert own.status_code == 200

    other = await client.get(
        "/api/v1/reports/timesheet",
        params={"month": f"{_MONTH_START:%Y-%m}", "user_id": str(factory.gestor.user_id)},
        headers=headers,
    )
    assert other.status_code == 403

    admin_view = await client.get(
        "/api/v1/reports/timesheet",
        params={"month": f"{_MONTH_START:%Y-%m}", "user_id": str(colaborador.user_id)},
        headers=factory.headers,
    )
    assert admin_view.status_code == 200


@pytest.mark.commits
async def test_expurgo_apos_12_meses(
    client: AsyncClient,
    factory: LawsuitFactory,
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    old_moment = datetime.now(UTC) - timedelta(days=400)
    recent_moment = datetime.now(UTC) - timedelta(days=1)
    await _seed_access_log(
        app_session_factory, factory.gestor.tenant_id, factory.gestor.user_id, old_moment
    )
    await _seed_access_log(
        app_session_factory, factory.gestor.tenant_id, factory.gestor.user_id, recent_moment
    )

    # Regra 9, exercitada por tenant (não por `purge_access_logs`, que varre todo o
    # banco — em suíte local com milhares de tenants acumulados de outras execuções
    # isso levava ~80 s por causa de `_purge_tenant` abrir uma engine por tenant).
    cutoff = datetime.now(UTC) - timedelta(days=365)
    deleted = await _purge_tenant(factory.gestor.tenant_id, cutoff)
    assert deleted >= 1

    remaining = await client.get(
        "/api/v1/reports/access-logs",
        params={"user_id": str(factory.gestor.user_id)},
        headers=factory.headers,
    )
    occurred_dates = [item["occurred_at"] for item in remaining.json()["items"]]
    assert all(
        datetime.fromisoformat(value) > datetime.now(UTC) - timedelta(days=365)
        for value in occurred_dates
    )


async def test_desligar_nao_apaga_historico(client: AsyncClient, factory: LawsuitFactory) -> None:
    await _create_account(client, factory.headers)
    await _set_tracking(client, factory.headers, True)
    await client.post(
        "/api/v1/auth/login",
        json={"email": factory.gestor.email, "password": factory.gestor.password},
        headers={"X-Tenant-Id": str(factory.gestor.tenant_id)},
    )
    await _set_tracking(client, factory.headers, False)

    response = await client.get("/api/v1/reports/access-logs", headers=factory.headers)
    assert response.json()["total"] == 1


async def test_tenant_a_nao_ve_access_logs_de_tenant_b(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    factory_a = await _make_factory(client, make_user, app_session_factory)
    factory_b = await _make_factory(client, make_user, app_session_factory)

    await _seed_access_log(
        app_session_factory,
        factory_a.gestor.tenant_id,
        factory_a.gestor.user_id,
        datetime.now(UTC),
    )

    response_b = await client.get("/api/v1/reports/access-logs", headers=factory_b.headers)
    assert response_b.json()["total"] == 0
