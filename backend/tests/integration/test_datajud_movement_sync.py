"""Sincronização de andamentos via DataJud (spec 047, §8) — as 12 regras de
negócio numeradas viram teste aqui: idempotência (regra 2), incremental (regra
3), sigilo (regra 4/6), pausa por não-encontrado (regra 5), capa que respeita o
dado do usuário (regra 8/12), lote resiliente (regra 9/11) e lock (regra 10).
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.locks import RedisSyncLock
from app.core.redis import create_redis_client
from app.core.rls import set_tenant_context
from app.domain.datajud.exceptions import LawsuitSyncInProgressError
from app.domain.datajud.movement_sync_service import MovementSyncService
from app.domain.datajud.service import DatajudService
from app.domain.integration_alerts.models import IntegrationAlert
from app.domain.lawsuits.cnj import compute_check_digit
from app.domain.lawsuits.models import Lawsuit, LawsuitMovement
from app.domain.lawsuits.repository import LawsuitRepository
from app.domain.users.models import UserRole
from app.integrations.datajud.client import DatajudClient
from app.integrations.http.client import ResilientHttpClient
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import (
    _auth_header,
    _create_lawsuit,
    _create_lawsuit_type,
    _create_stage,
)

SessionFactory = async_sessionmaker[AsyncSession]
API_KEY = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
BASE_URL = "https://api-publica.datajud.cnj.jus.br"


def _cnj(seq: int) -> str:
    """Número CNJ válido do segmento 8 (Estadual) / TR 26 (SP) — infer_court_code
    resolve pra TJSP (spec 025), o mesmo tribunal usado em todo este arquivo."""
    sequential, year, segment, court, origin = f"{seq:07d}", "2026", "8", "26", "0100"
    digits18 = sequential + year + segment + court + origin
    return sequential + compute_check_digit(digits18) + year + segment + court + origin


def make_movement(
    code: int,
    name: str,
    occurred_at: datetime,
    *,
    organ_code: str = "111",
    organ_name: str = "1ª Vara Cível",
) -> dict[str, object]:
    return {
        "codigo": code,
        "nome": name,
        "dataHora": occurred_at.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "orgaoJulgador": {"codigoOrgao": organ_code, "nomeOrgao": organ_name},
    }


def make_payload(
    *,
    process_number: str,
    nivel_sigilo: int = 0,
    last_update: datetime | None,
    movements: list[dict[str, object]] | None = None,
    organ_name: str = "1ª Vara Cível",
    filing_date: str = "20260101090000",
    hits: bool = True,
) -> dict[str, object]:
    if not hits:
        return {"hits": {"total": {"value": 0}, "hits": []}}
    source: dict[str, object] = {
        "id": f"TJSP_JE_{process_number}",
        "tribunal": "TJSP",
        "grau": "JE",
        "numeroProcesso": process_number,
        "dataAjuizamento": filing_date,
        "nivelSigilo": nivel_sigilo,
        "orgaoJulgador": {"codigo": 111, "nome": organ_name, "codigoMunicipioIBGE": 3550308},
        "classe": {"codigo": 436, "nome": "Procedimento Comum"},
        "sistema": {"codigo": 4, "nome": "Projudi"},
        "formato": {"codigo": 1, "nome": "Eletrônico"},
        "assuntos": [{"codigo": 7768, "nome": "Rescisão do contrato"}],
        "movimentos": movements or [],
    }
    if last_update is not None:
        source["dataHoraUltimaAtualizacao"] = last_update.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return {"hits": {"total": {"value": 1}, "hits": [{"_source": source}]}}


@dataclass
class SyncSetup:
    client: AsyncClient
    sessions: SessionFactory
    gestor: SeededUser
    headers: dict[str, str]
    type_id: str
    stage_id: str

    async def create_lawsuit(self, *, process_number: str, **extra: object) -> uuid.UUID:
        lawsuit = await _create_lawsuit(
            self.client,
            self.headers,
            user_id=str(self.gestor.user_id),
            lawsuit_type_id=self.type_id,
            stage_id=self.stage_id,
            process_number=process_number,
            **extra,
        )
        return uuid.UUID(str(lawsuit["id"]))

    async def archive(self, lawsuit_id: uuid.UUID) -> None:
        async with self.sessions() as session, session.begin():
            await set_tenant_context(session, self.gestor.tenant_id)
            await session.execute(
                text("UPDATE lawsuits SET is_archived = true WHERE id = CAST(:id AS uuid)"),
                {"id": str(lawsuit_id)},
            )

    async def set_judging_organ(self, lawsuit_id: uuid.UUID, value: str) -> None:
        async with self.sessions() as session, session.begin():
            await set_tenant_context(session, self.gestor.tenant_id)
            await session.execute(
                text("UPDATE lawsuits SET judging_organ = :value WHERE id = CAST(:id AS uuid)"),
                {"id": str(lawsuit_id), "value": value},
            )


@pytest.fixture
async def setup(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: SessionFactory,
) -> SyncSetup:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    return SyncSetup(client, app_session_factory, gestor, headers, type_id, stage_id)


def make_service(
    session: AsyncSession, tenant_id: uuid.UUID, handler: httpx.MockTransport
) -> MovementSyncService:
    http = ResilientHttpClient(transport=handler)
    datajud_client = DatajudClient(http=http, base_url=BASE_URL, api_key=API_KEY)
    datajud_service = DatajudService(session, datajud_client)
    return MovementSyncService(session, tenant_id, datajud_service)


def json_handler(payload: dict[str, object]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


async def get_lawsuit(
    factory: SessionFactory, tenant_id: uuid.UUID, lawsuit_id: uuid.UUID
) -> Lawsuit:
    async with factory() as session:
        await set_tenant_context(session, tenant_id)
        lawsuit = await session.get(Lawsuit, lawsuit_id)
        assert lawsuit is not None
        _ = (
            lawsuit.datajud_last_sync_at,
            lawsuit.datajud_last_update,
            lawsuit.datajud_not_found_count,
            lawsuit.judging_organ,
            lawsuit.filing_date,
            lawsuit.process_date,
            lawsuit.cnj_class_code,
            lawsuit.cnj_class_name,
            lawsuit.last_movement_at,
        )
        return lawsuit


async def count_movements(
    factory: SessionFactory, tenant_id: uuid.UUID, lawsuit_id: uuid.UUID
) -> int:
    async with factory() as session:
        await set_tenant_context(session, tenant_id)
        rows = await session.scalars(
            select(LawsuitMovement).where(LawsuitMovement.lawsuit_id == lawsuit_id)
        )
        return len(rows.all())


async def test_primeira_sync_traz_todos_os_movimentos(setup: SyncSetup) -> None:
    number = _cnj(1)
    lawsuit_id = await setup.create_lawsuit(process_number=number)
    now = datetime.now(UTC).replace(microsecond=0)
    movements = [
        make_movement(26, "Distribuição", now - timedelta(days=3)),
        make_movement(51, "Conclusão", now - timedelta(days=2)),
        make_movement(848, "Trânsito em julgado", now - timedelta(days=1)),
    ]
    payload = make_payload(process_number=number, last_update=now, movements=movements)

    async with setup.sessions() as session, session.begin():
        await set_tenant_context(session, setup.gestor.tenant_id)
        lawsuit = await session.get(Lawsuit, lawsuit_id)
        assert lawsuit is not None
        service = make_service(session, setup.gestor.tenant_id, json_handler(payload))
        result = await service.sync_lawsuit(lawsuit)

    assert result.status == "synced"
    assert result.new_movements == 3
    assert await count_movements(setup.sessions, setup.gestor.tenant_id, lawsuit_id) == 3


async def test_rodar_duas_vezes_nao_duplica(setup: SyncSetup) -> None:
    """Regra 2: dedup por external_id — testado isolado do filtro incremental
    (regra 3) resetando `datajud_last_update` antes do segundo processamento, pra
    provar que o dedup em si (não só o filtro de data) segura a duplicata."""
    number = _cnj(2)
    lawsuit_id = await setup.create_lawsuit(process_number=number)
    now = datetime.now(UTC).replace(microsecond=0)
    movements = [make_movement(26, "Distribuição", now - timedelta(days=1))]
    payload = make_payload(process_number=number, last_update=now, movements=movements)

    async with setup.sessions() as session, session.begin():
        await set_tenant_context(session, setup.gestor.tenant_id)
        lawsuit = await session.get(Lawsuit, lawsuit_id)
        assert lawsuit is not None
        service = make_service(session, setup.gestor.tenant_id, json_handler(payload))
        first = await service.sync_lawsuit(lawsuit)
        lawsuit.datajud_last_update = None  # isola o dedup do filtro incremental
        second = await service.sync_lawsuit(lawsuit)

    assert first.new_movements == 1
    assert second.new_movements == 0
    assert await count_movements(setup.sessions, setup.gestor.tenant_id, lawsuit_id) == 1


async def test_incremental_ignora_movimento_antigo(setup: SyncSetup) -> None:
    number = _cnj(3)
    lawsuit_id = await setup.create_lawsuit(process_number=number)
    t1 = datetime.now(UTC).replace(microsecond=0) - timedelta(days=5)
    t2 = t1 + timedelta(days=1)
    t3 = t2 + timedelta(days=1)
    first_payload = make_payload(
        process_number=number,
        last_update=t2,
        movements=[make_movement(26, "Distribuição", t1), make_movement(51, "Conclusão", t2)],
    )
    second_payload = make_payload(
        process_number=number,
        last_update=t3,
        movements=[
            make_movement(26, "Distribuição", t1),
            make_movement(51, "Conclusão", t2),
            make_movement(848, "Trânsito em julgado", t3),
        ],
    )

    async with setup.sessions() as session, session.begin():
        await set_tenant_context(session, setup.gestor.tenant_id)
        lawsuit = await session.get(Lawsuit, lawsuit_id)
        assert lawsuit is not None
        service = make_service(session, setup.gestor.tenant_id, json_handler(first_payload))
        first = await service.sync_lawsuit(lawsuit)
        service = make_service(session, setup.gestor.tenant_id, json_handler(second_payload))
        second = await service.sync_lawsuit(lawsuit)

    assert first.new_movements == 2
    assert second.new_movements == 1  # só o de t3 — t1/t2 já passaram
    assert await count_movements(setup.sessions, setup.gestor.tenant_id, lawsuit_id) == 3


async def test_sem_mudanca_nao_escreve_nada(setup: SyncSetup) -> None:
    number = _cnj(4)
    lawsuit_id = await setup.create_lawsuit(process_number=number)
    now = datetime.now(UTC).replace(microsecond=0)
    payload = make_payload(
        process_number=number, last_update=now, movements=[make_movement(26, "Distribuição", now)]
    )

    async with setup.sessions() as session, session.begin():
        await set_tenant_context(session, setup.gestor.tenant_id)
        lawsuit = await session.get(Lawsuit, lawsuit_id)
        assert lawsuit is not None
        service = make_service(session, setup.gestor.tenant_id, json_handler(payload))
        first = await service.sync_lawsuit(lawsuit)
        second = await service.sync_lawsuit(lawsuit)

    assert first.status == "synced"
    assert second.status == "unchanged"
    assert second.new_movements == 0
    assert await count_movements(setup.sessions, setup.gestor.tenant_id, lawsuit_id) == 1


async def test_segredo_de_justica_nao_persiste(setup: SyncSetup) -> None:
    number = _cnj(5)
    lawsuit_id = await setup.create_lawsuit(process_number=number)
    payload = make_payload(
        process_number=number,
        nivel_sigilo=1,
        last_update=datetime.now(UTC),
        movements=[make_movement(26, "Distribuição", datetime.now(UTC))],
    )

    async with setup.sessions() as session, session.begin():
        await set_tenant_context(session, setup.gestor.tenant_id)
        lawsuit = await session.get(Lawsuit, lawsuit_id)
        assert lawsuit is not None
        service = make_service(session, setup.gestor.tenant_id, json_handler(payload))
        result = await service.sync_lawsuit(lawsuit)

    assert result.status == "sealed"
    assert await count_movements(setup.sessions, setup.gestor.tenant_id, lawsuit_id) == 0
    updated = await get_lawsuit(setup.sessions, setup.gestor.tenant_id, lawsuit_id)
    assert updated.datajud_not_found_count == 5  # regra 4: não sincronizável, sem esperar 5x


async def test_cinco_nao_encontrados_pausa_e_alerta(setup: SyncSetup) -> None:
    number = _cnj(6)
    lawsuit_id = await setup.create_lawsuit(process_number=number)
    not_found_payload = make_payload(process_number=number, last_update=None, hits=False)

    async with setup.sessions() as session, session.begin():
        await set_tenant_context(session, setup.gestor.tenant_id)
        lawsuit = await session.get(Lawsuit, lawsuit_id)
        assert lawsuit is not None
        service = make_service(session, setup.gestor.tenant_id, json_handler(not_found_payload))
        for _ in range(5):
            result = await service.sync_lawsuit(lawsuit)

        assert result.status == "not_found"
        alert = (
            await session.scalars(
                select(IntegrationAlert).where(IntegrationAlert.code == "process_not_found")
            )
        ).one()
        assert alert.tenant_id == setup.gestor.tenant_id
        assert alert.severity == "warning"

        due = await LawsuitRepository(session).list_due_for_datajud_sync(limit=100)
        assert lawsuit_id not in {item.id for item in due}  # regra 5: pausado, saiu da fila


async def test_capa_nao_sobrescreve_campo_preenchido(setup: SyncSetup) -> None:
    number = _cnj(7)
    lawsuit_id = await setup.create_lawsuit(process_number=number)
    await setup.set_judging_organ(lawsuit_id, "Vara Pré-Existente")
    payload = make_payload(
        process_number=number, last_update=datetime.now(UTC), organ_name="Vara Nova do CNJ"
    )

    async with setup.sessions() as session, session.begin():
        await set_tenant_context(session, setup.gestor.tenant_id)
        lawsuit = await session.get(Lawsuit, lawsuit_id)
        assert lawsuit is not None
        service = make_service(session, setup.gestor.tenant_id, json_handler(payload))
        await service.sync_lawsuit(lawsuit)

    updated = await get_lawsuit(setup.sessions, setup.gestor.tenant_id, lawsuit_id)
    assert updated.judging_organ == "Vara Pré-Existente"  # não sobrescrito
    assert updated.cnj_class_code == 436  # campo vazio antes → populado normalmente
    assert updated.cnj_class_name == "Procedimento Comum"


async def test_filing_date_nao_toca_process_date(setup: SyncSetup) -> None:
    number = _cnj(8)
    lawsuit_id = await setup.create_lawsuit(process_number=number, process_date="2020-05-10")
    payload = make_payload(
        process_number=number, last_update=datetime.now(UTC), filing_date="20260315093000"
    )

    async with setup.sessions() as session, session.begin():
        await set_tenant_context(session, setup.gestor.tenant_id)
        lawsuit = await session.get(Lawsuit, lawsuit_id)
        assert lawsuit is not None
        service = make_service(session, setup.gestor.tenant_id, json_handler(payload))
        await service.sync_lawsuit(lawsuit)

    updated = await get_lawsuit(setup.sessions, setup.gestor.tenant_id, lawsuit_id)
    assert updated.process_date is not None and updated.process_date.isoformat() == "2020-05-10"
    assert updated.filing_date is not None and updated.filing_date.isoformat() == "2026-03-15"


async def test_last_movement_at_atualiza_pela_trigger(setup: SyncSetup) -> None:
    number = _cnj(9)
    lawsuit_id = await setup.create_lawsuit(process_number=number)
    now = datetime.now(UTC).replace(microsecond=0)
    latest = now - timedelta(hours=1)
    payload = make_payload(
        process_number=number,
        last_update=now,
        movements=[
            make_movement(26, "Distribuição", now - timedelta(days=2)),
            make_movement(848, "Trânsito em julgado", latest),
        ],
    )

    async with setup.sessions() as session, session.begin():
        await set_tenant_context(session, setup.gestor.tenant_id)
        lawsuit = await session.get(Lawsuit, lawsuit_id)
        assert lawsuit is not None
        service = make_service(session, setup.gestor.tenant_id, json_handler(payload))
        await service.sync_lawsuit(lawsuit)

    updated = await get_lawsuit(setup.sessions, setup.gestor.tenant_id, lawsuit_id)
    assert updated.last_movement_at == latest


async def test_falha_em_um_nao_interrompe_o_lote(setup: SyncSetup) -> None:
    good_number = _cnj(10)
    bad_number = _cnj(11)
    good_id = await setup.create_lawsuit(process_number=good_number)
    bad_id = await setup.create_lawsuit(process_number=bad_number)
    now = datetime.now(UTC)
    good_payload = make_payload(
        process_number=good_number,
        last_update=now,
        movements=[make_movement(26, "Distribuição", now)],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        if bad_number in body:
            return httpx.Response(500, content=b"erro simulado")
        return httpx.Response(200, json=good_payload)

    async with setup.sessions() as session, session.begin():
        await set_tenant_context(session, setup.gestor.tenant_id)
        service = make_service(session, setup.gestor.tenant_id, httpx.MockTransport(handler))
        results = await service.sync_due(batch_size=10)

    by_id = {result.lawsuit_id: result for result in results}
    assert {good_id, bad_id} <= set(by_id)
    assert by_id[good_id].status == "synced"
    assert by_id[bad_id].status == "error"


async def test_sync_manual_concorrente_retorna_409(setup: SyncSetup) -> None:
    number = _cnj(12)
    lawsuit_id = await setup.create_lawsuit(process_number=number)
    now = datetime.now(UTC)
    payload = make_payload(
        process_number=number, last_update=now, movements=[make_movement(26, "Distribuição", now)]
    )
    redis: Redis = create_redis_client()
    try:
        async with setup.sessions() as session, session.begin():
            await set_tenant_context(session, setup.gestor.tenant_id)
            lawsuit = await session.get(Lawsuit, lawsuit_id)
            assert lawsuit is not None
            service = make_service(session, setup.gestor.tenant_id, json_handler(payload))
            holder = RedisSyncLock(redis)
            assert await holder.acquire(f"rito:datajud_sync:{lawsuit_id}", ttl_seconds=60)

            with pytest.raises(LawsuitSyncInProgressError):
                await service.sync_lawsuit_locked(lawsuit, RedisSyncLock(redis))

            await holder.release(f"rito:datajud_sync:{lawsuit_id}")
            result = await service.sync_lawsuit_locked(lawsuit, RedisSyncLock(redis))
            assert result.status == "synced"
    finally:
        await redis.aclose()


async def test_movimento_aparece_na_timeline(setup: SyncSetup) -> None:
    number = _cnj(13)
    lawsuit_id = await setup.create_lawsuit(process_number=number)
    now = datetime.now(UTC).replace(microsecond=0)
    payload = make_payload(
        process_number=number,
        last_update=now,
        movements=[make_movement(26, "Distribuição", now)],
    )

    async with setup.sessions() as session, session.begin():
        await set_tenant_context(session, setup.gestor.tenant_id)
        lawsuit = await session.get(Lawsuit, lawsuit_id)
        assert lawsuit is not None
        service = make_service(session, setup.gestor.tenant_id, json_handler(payload))
        await service.sync_lawsuit(lawsuit)

    response = await setup.client.get(
        f"/api/v1/lawsuits/{lawsuit_id}/timeline", headers=setup.headers
    )
    assert response.status_code == 200
    kinds = [item["kind"] for item in response.json()["items"]]
    assert "movement_auto" in kinds


async def test_processo_arquivado_fora_da_fila(setup: SyncSetup) -> None:
    archived_id = await setup.create_lawsuit(process_number=_cnj(14))
    active_id = await setup.create_lawsuit(process_number=_cnj(15))
    await setup.archive(archived_id)

    async with setup.sessions() as session:
        await set_tenant_context(session, setup.gestor.tenant_id)
        due = await LawsuitRepository(session).list_due_for_datajud_sync(limit=100)

    due_ids = {item.id for item in due}
    assert active_id in due_ids
    assert archived_id not in due_ids
