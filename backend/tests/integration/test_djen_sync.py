"""Sincronização DJEN: dedup, cancelamento, janelas, falhas, lock e runs (spec 044, §8).

Nenhuma chamada de rede: a fonte é um fake `PublicationSource` servindo itens
parseados das fixtures gravadas. O lock usa o Redis de teste (db 15) — infra
local, como Postgres/MinIO (ver tests/conftest.py).
"""

import json
import uuid
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Registra `lawsuits` no metadata do Base: sem o import, a FK publications.lawsuit_id
# não resolve no flush (testes que usam a fixture `client` recebem isso via app.main).
import app.domain.lawsuits.models  # noqa: F401
from app.core.locks import RedisSyncLock
from app.core.redis import create_redis_client
from app.core.rls import set_tenant_context
from app.domain.monitored_terms.models import (
    MonitoredTerm,
    TermKind,
    TermStatus,
    TermSyncRun,
)
from app.domain.monitored_terms.sync import (
    MAX_WINDOW_DAYS,
    PublicationPage,
    TermSyncService,
)
from app.domain.publications.models import (
    Publication,
    PublicationLawyer,
    PublicationRecipient,
)
from app.domain.publications.service import PublicationService
from app.domain.users.models import UserRole
from app.integrations.djen.parser import ParsedCommunication, parse_communication
from tests.integration.conftest import SeededUser

SessionFactory = async_sessionmaker[AsyncSession]
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "http" / "comunicaapi.pje.jus.br"
TODAY = date.today


class FakeSource:
    """PublicationSource de teste: serve páginas (ou erros) na ordem enfileirada
    e registra cada chamada — é o que permite afirmar janela, página e contagem
    sem rede."""

    def __init__(self) -> None:
        self.calls: list[tuple[date, date, int]] = []
        self._queue: deque[PublicationPage | Exception] = deque()

    def queue_page(self, items: list[ParsedCommunication], count: int | None = None) -> None:
        total = count if count is not None else len(items)
        self._queue.append(PublicationPage(count=total, items=items))

    def queue_error(self, message: str = "DJEN fora do ar") -> None:
        self._queue.append(RuntimeError(message))

    async def fetch(
        self, *, term: MonitoredTerm, start: date, end: date, page: int
    ) -> PublicationPage:
        self.calls.append((start, end, page))
        assert self._queue, f"fetch inesperado: {start}..{end} página {page}"
        result = self._queue.popleft()
        if isinstance(result, Exception):
            raise result
        return result


@dataclass
class TermSnapshot:
    status: TermStatus
    status_message: str | None
    last_sync_at: datetime | None
    last_success_at: datetime | None
    next_sync_at: datetime | None
    last_captured_date: date | None


def fixture_items(name: str, limit: int) -> list[ParsedCommunication]:
    payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return [parse_communication(item) for item in payload["items"][:limit]]


def synthetic_item(seq: int, *, cancelled: bool = False) -> ParsedCommunication:
    """Item DJEN sintético com destinatário e advogado — hash estável por `seq`
    (a deduplicação por hash é o que está sob teste)."""
    availability = TODAY().isoformat()
    # Any: item bruto do DJEN, como o parser espera (dict de JSON arbitrário).
    raw: dict[str, Any] = {
        "id": 900_000_000 + seq,
        "hash": f"sync-test-{seq:05d}",
        "data_disponibilizacao": availability,
        "siglaTribunal": "TJSP",
        "tipoComunicacao": "Intimação",
        "texto": f"Texto da intimação {seq}",
        "destinatarios": [{"nome": f"PARTE TESTE {seq}", "polo": "A"}],
        "destinatarioadvogados": [
            {
                "advogado_id": 7_000_000 + seq,
                "advogado": {
                    "nome": f"ADVOGADO {seq}",
                    "numero_oab": "114962",
                    "uf_oab": "MG",
                },
            }
        ],
    }
    if cancelled:
        raw.update(
            {
                "ativo": False,
                "status": "C",
                "motivo_cancelamento": "Publicação anulada a pedido da parte",
                "data_cancelamento": availability,
            }
        )
    return parse_communication(raw)


async def make_term(
    factory: SessionFactory,
    tenant_id: uuid.UUID,
    *,
    value: str = "114962",
    backfill_days: int = 30,
    last_captured_date: date | None = None,
) -> uuid.UUID:
    async with factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        term = MonitoredTerm(
            tenant_id=tenant_id,
            kind=TermKind.OAB,
            value=value,
            oab_state="MG",
            status=TermStatus.PENDENTE,
            backfill_from=TODAY() - timedelta(days=backfill_days),
            last_captured_date=last_captured_date,
            next_sync_at=datetime.now(UTC),
        )
        session.add(term)
        await session.flush()
        return term.id


async def fetch_term(
    factory: SessionFactory, tenant_id: uuid.UUID, term_id: uuid.UUID
) -> TermSnapshot:
    async with factory() as session:
        await set_tenant_context(session, tenant_id)
        term = await session.get(MonitoredTerm, term_id)
        assert term is not None
        return TermSnapshot(
            status=term.status,
            status_message=term.status_message,
            last_sync_at=term.last_sync_at,
            last_success_at=term.last_success_at,
            next_sync_at=term.next_sync_at,
            last_captured_date=term.last_captured_date,
        )


async def fetch_runs(
    factory: SessionFactory, tenant_id: uuid.UUID, term_id: uuid.UUID
) -> list[TermSyncRun]:
    async with factory() as session:
        await set_tenant_context(session, tenant_id)
        result = await session.scalars(
            select(TermSyncRun)
            .where(TermSyncRun.term_id == term_id)
            .order_by(TermSyncRun.started_at)
        )
        runs = list(result.all())
        for run in runs:  # carrega na sessão — depois do close o acesso seria lazy
            _ = (run.found_count, run.new_count, run.error, run.finished_at)
        return runs


async def count_rows(factory: SessionFactory, tenant_id: uuid.UUID, model: type) -> int:
    async with factory() as session:
        await set_tenant_context(session, tenant_id)
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def run_sync(
    factory: SessionFactory,
    tenant_id: uuid.UUID,
    term_id: uuid.UUID,
    source: FakeSource,
    *,
    lock: RedisSyncLock | None = None,
    now: datetime | None = None,
) -> TermSyncRun | None:
    """Invoca o service como o worker faria: sessão crua, o service gerencia
    commits e o contexto de tenant."""
    async with factory() as session:
        service = TermSyncService(session, tenant_id, source, lock=lock)
        return await service.sync_term(MonitoredTerm(id=term_id), now=now)


async def test_primeira_sync_persiste_publicacoes(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    term_id = await make_term(app_session_factory, tenant_id)
    items = fixture_items("oab_mg.json", 3)
    source = FakeSource()
    source.queue_page(items)

    started = datetime.now(UTC)
    run = await run_sync(app_session_factory, tenant_id, term_id, source)

    assert run is not None and run.error is None and run.finished_at is not None
    assert run.found_count == 3 and run.new_count == 3
    # Regra 4: primeira execução usa backfill_from; janela termina hoje.
    assert source.calls == [(TODAY() - timedelta(days=30), TODAY(), 1)]

    term = await fetch_term(app_session_factory, tenant_id, term_id)
    assert term.status is TermStatus.ATIVO
    assert term.last_captured_date == TODAY()
    assert term.last_success_at is not None and term.last_success_at >= started
    assert term.next_sync_at is not None and term.next_sync_at > started

    assert await count_rows(app_session_factory, tenant_id, Publication) == 3
    assert await count_rows(app_session_factory, tenant_id, PublicationRecipient) == sum(
        len(item.recipients) for item in items
    )
    assert await count_rows(app_session_factory, tenant_id, PublicationLawyer) == sum(
        len(item.lawyers) for item in items
    )


async def test_rodar_duas_vezes_nao_duplica(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    """Regra 1: deduplicação por (tenant_id, hash) — reprocessar a mesma janela
    não cria linha nova."""
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    term_id = await make_term(app_session_factory, tenant_id)
    items = fixture_items("oab_mg.json", 3)
    source = FakeSource()
    source.queue_page(items)
    source.queue_page(items)  # segunda execução recebe o MESMO payload

    first = await run_sync(app_session_factory, tenant_id, term_id, source)
    second = await run_sync(app_session_factory, tenant_id, term_id, source)

    assert first is not None and first.new_count == 3
    assert second is not None and second.error is None
    assert second.found_count == 3 and second.new_count == 0
    assert await count_rows(app_session_factory, tenant_id, Publication) == 3
    # Regra 3: a segunda janela partiu de last_captured_date com 1 dia de overlap.
    assert source.calls[1] == (TODAY() - timedelta(days=1), TODAY(), 1)


async def test_janela_incremental_com_sobreposicao_de_um_dia(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    captured = TODAY() - timedelta(days=5)
    term_id = await make_term(app_session_factory, tenant_id, last_captured_date=captured)
    source = FakeSource()
    source.queue_page([])

    run = await run_sync(app_session_factory, tenant_id, term_id, source)

    assert run is not None and run.error is None
    assert source.calls == [(captured - timedelta(days=1), TODAY(), 1)]


async def test_cancelamento_marca_inativa_e_grava_motivo(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    """Regra 2: o item volta com ativo=false/motivo — a publicação existente vira
    is_active=false, com motivo e data, e NÃO é apagada."""
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    term_id = await make_term(app_session_factory, tenant_id)
    source = FakeSource()
    source.queue_page([synthetic_item(1)])
    source.queue_page([synthetic_item(1, cancelled=True)])  # mesmo hash, anulada

    await run_sync(app_session_factory, tenant_id, term_id, source)
    second = await run_sync(app_session_factory, tenant_id, term_id, source)

    assert second is not None and second.new_count == 0
    async with app_session_factory() as session:
        await set_tenant_context(session, tenant_id)
        publication = await session.scalar(select(Publication))
        assert publication is not None
        assert publication.is_active is False
        assert publication.cancellation_reason == "Publicação anulada a pedido da parte"
        assert publication.cancelled_at == TODAY()
        assert publication.status == "C"
    # Não apagada:
    assert await count_rows(app_session_factory, tenant_id, Publication) == 1


async def test_publicacao_que_chega_cancelada_e_persistida_inativa(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    """Regra 2 na borda: primeira vez que o hash aparece já é como anulada —
    persiste inativa (ela existiu no DJEN; sumir com ela perderia o rastro)."""
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    term_id = await make_term(app_session_factory, tenant_id)
    source = FakeSource()
    source.queue_page(fixture_items("cancelada.json", 1))

    run = await run_sync(app_session_factory, tenant_id, term_id, source)

    assert run is not None and run.new_count == 1
    async with app_session_factory() as session:
        await set_tenant_context(session, tenant_id)
        publication = await session.scalar(select(Publication))
        assert publication is not None
        assert publication.is_active is False
        assert publication.cancellation_reason is not None


async def test_falha_em_um_termo_nao_afeta_os_outros(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    """Regra 5: cada termo é uma unidade de trabalho isolada."""
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    failing = await make_term(app_session_factory, tenant_id, value="114962")
    healthy = await make_term(app_session_factory, tenant_id, value="999001")
    source = FakeSource()
    source.queue_error("timeout no DJEN")
    source.queue_page([synthetic_item(10)])

    async with app_session_factory() as session:
        service = TermSyncService(session, tenant_id, source)
        runs = await service.sync_terms([MonitoredTerm(id=failing), MonitoredTerm(id=healthy)])

    assert len(runs) == 2
    failing_term = await fetch_term(app_session_factory, tenant_id, failing)
    healthy_term = await fetch_term(app_session_factory, tenant_id, healthy)
    assert failing_term.status is TermStatus.FALHA
    assert failing_term.status_message == "timeout no DJEN"
    assert healthy_term.status is TermStatus.ATIVO
    assert await count_rows(app_session_factory, tenant_id, Publication) == 1


async def test_falha_marca_falha_e_sucesso_volta_ativo(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    """Regra 6: falha marca FALHA com a mensagem; a execução seguinte bem-sucedida
    devolve o termo a ATIVO e limpa a mensagem."""
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    term_id = await make_term(app_session_factory, tenant_id)
    source = FakeSource()
    source.queue_error("500 persistente")

    failed_run = await run_sync(app_session_factory, tenant_id, term_id, source)

    assert failed_run is not None
    assert failed_run.error == "500 persistente" and failed_run.finished_at is not None
    term = await fetch_term(app_session_factory, tenant_id, term_id)
    assert term.status is TermStatus.FALHA
    assert term.status_message == "500 persistente"
    assert term.last_success_at is None
    assert term.next_sync_at is not None  # continua agendado — a falha não aposenta o termo

    source.queue_page([synthetic_item(20)])
    recovered_run = await run_sync(app_session_factory, tenant_id, term_id, source)

    assert recovered_run is not None and recovered_run.error is None
    term = await fetch_term(app_session_factory, tenant_id, term_id)
    assert term.status is TermStatus.ATIVO
    assert term.status_message is None
    assert term.last_success_at is not None


async def test_lock_impede_execucao_concorrente(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    """Regra 10: lock em Redis por termo — quem não adquire desiste (None) e não
    cria run; depois de liberado, a execução segue normal."""
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    term_id = await make_term(app_session_factory, tenant_id)
    redis = create_redis_client()
    holder = RedisSyncLock(redis)
    key = f"rito:djen_sync:{term_id}"
    try:
        assert await holder.acquire(key, ttl_seconds=60) is True

        source = FakeSource()  # nem chega a ser consultado
        skipped = await run_sync(
            app_session_factory, tenant_id, term_id, source, lock=RedisSyncLock(redis)
        )

        assert skipped is None
        assert source.calls == []
        assert await fetch_runs(app_session_factory, tenant_id, term_id) == []

        await holder.release(key)
        source.queue_page([synthetic_item(30)])
        ran = await run_sync(
            app_session_factory, tenant_id, term_id, source, lock=RedisSyncLock(redis)
        )
        assert ran is not None and ran.new_count == 1
    finally:
        await redis.aclose()


async def test_paginacao_percorre_todas_as_paginas(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    term_id = await make_term(app_session_factory, tenant_id)
    source = FakeSource()
    source.queue_page([synthetic_item(seq) for seq in range(100)], count=230)
    source.queue_page([synthetic_item(seq) for seq in range(100, 200)], count=230)
    source.queue_page([synthetic_item(seq) for seq in range(200, 230)], count=230)

    run = await run_sync(app_session_factory, tenant_id, term_id, source)

    assert run is not None and run.error is None
    assert [page for _, _, page in source.calls] == [1, 2, 3]
    assert run.found_count == 230 and run.new_count == 230
    assert await count_rows(app_session_factory, tenant_id, Publication) == 230


async def test_pagina_parcial_nao_persiste_pela_metade(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: SessionFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regra 9: a página é a unidade transacional. Falha no 2º item da página 2
    descarta a página 2 inteira; a página 1 (já commitada) fica — e o re-run
    não a duplica."""
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    # 91 dias de backfill → 2 fatias (regra 12), 1 página de 2 itens por fatia.
    term_id = await make_term(app_session_factory, tenant_id, backfill_days=91)

    original_register = PublicationService.register
    state = {"calls": 0, "fail_on_call": 4}  # fatia 1: calls 1-2; fatia 2: call 4 falha

    async def maybe_failing_register(
        self: PublicationService, parsed: ParsedCommunication
    ) -> Publication:
        state["calls"] += 1
        if state["calls"] == state["fail_on_call"]:
            raise RuntimeError("falha simulada no meio da página")
        return await original_register(self, parsed)

    monkeypatch.setattr(PublicationService, "register", maybe_failing_register)

    source = FakeSource()
    source.queue_page([synthetic_item(1), synthetic_item(2)], count=2)
    source.queue_page([synthetic_item(3), synthetic_item(4)], count=2)

    failed_run = await run_sync(app_session_factory, tenant_id, term_id, source)

    assert failed_run is not None and failed_run.error is not None
    assert await count_rows(app_session_factory, tenant_id, Publication) == 2  # só a fatia 1
    assert (await fetch_term(app_session_factory, tenant_id, term_id)).status is TermStatus.FALHA

    state["fail_on_call"] = -1  # desliga a falha
    # O re-run parte de last_captured_date (fim da fatia 1) com 1 dia de overlap:
    # uma única fatia — os 4 itens voltam na mesma página.
    source.queue_page(
        [synthetic_item(1), synthetic_item(2), synthetic_item(3), synthetic_item(4)], count=4
    )
    recovered_run = await run_sync(app_session_factory, tenant_id, term_id, source)

    assert recovered_run is not None and recovered_run.error is None
    assert recovered_run.new_count == 2  # a fatia 1 foi dedupada, não duplicada
    assert await count_rows(app_session_factory, tenant_id, Publication) == 4


async def test_backfill_de_12_meses_e_fatiado_em_janelas_de_90_dias(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    """Regra 12: janela máxima de 90 dias por fatia — um backfill de 12 meses
    vira fatias sequenciais e contíguas, e last_captured_date avança a cada uma."""
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    backfill = TODAY() - timedelta(days=365)
    term_id = await make_term(app_session_factory, tenant_id, backfill_days=365)
    source = FakeSource()
    for seq in range(5):  # 366 dias em fatias de 91: 4×91 + 2 → 5 fatias
        source.queue_page([synthetic_item(100 + seq)], count=1)

    run = await run_sync(app_session_factory, tenant_id, term_id, source)

    assert run is not None and run.error is None
    assert len(source.calls) == 5
    assert source.calls[0][0] == backfill
    for (start, end, page), (next_start, _, _) in zip(source.calls, source.calls[1:], strict=False):
        assert (end - start).days <= MAX_WINDOW_DAYS
        assert next_start == end + timedelta(days=1)  # fatias contíguas, sem buraco
        assert page == 1
    assert source.calls[-1][1] == TODAY()
    term = await fetch_term(app_session_factory, tenant_id, term_id)
    assert term.last_captured_date == TODAY()
    assert await count_rows(app_session_factory, tenant_id, Publication) == 5


async def test_sem_itens_atualiza_last_success_at(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    """Regra 11: silêncio é resultado válido — janela vazia ainda fecha a run,
    marca sucesso e avança a captura."""
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    term_id = await make_term(app_session_factory, tenant_id)
    source = FakeSource()
    source.queue_page([], count=0)

    run = await run_sync(app_session_factory, tenant_id, term_id, source)

    assert run is not None and run.error is None
    assert run.found_count == 0 and run.new_count == 0
    term = await fetch_term(app_session_factory, tenant_id, term_id)
    assert term.status is TermStatus.ATIVO
    assert term.last_success_at is not None
    assert term.last_captured_date == TODAY()


async def test_term_sync_runs_registra_contadores(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    term_id = await make_term(app_session_factory, tenant_id)
    source = FakeSource()
    source.queue_page(fixture_items("oab_mg.json", 2))

    await run_sync(app_session_factory, tenant_id, term_id, source)

    runs = await fetch_runs(app_session_factory, tenant_id, term_id)
    assert len(runs) == 1
    run = runs[0]
    assert run.found_count == 2 and run.new_count == 2
    assert run.error is None and run.finished_at is not None


async def test_run_aberta_do_sync_manual_e_reutilizada(
    make_user: Callable[..., Awaitable[SeededUser]], app_session_factory: SessionFactory
) -> None:
    """Descoberta da 043: o sync manual abre a run sem processar — a varredura
    consome ESSA run (não cria outra) e a fecha com os contadores."""
    gestor = await make_user(role=UserRole.GESTOR)
    tenant_id = gestor.tenant_id
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, gestor.tenant_id)
        term = MonitoredTerm(
            tenant_id=gestor.tenant_id,
            kind=TermKind.OAB,
            value="114962",
            oab_state="MG",
            status=TermStatus.SINCRONIZANDO,
            backfill_from=TODAY() - timedelta(days=30),
            next_sync_at=datetime.now(UTC),
        )
        session.add(term)
        await session.flush()
        session.add(TermSyncRun(tenant_id=gestor.tenant_id, term_id=term.id))
        await session.flush()
        term_id = term.id

    source = FakeSource()
    source.queue_page([synthetic_item(50)])
    run = await run_sync(app_session_factory, tenant_id, term_id, source)

    runs = await fetch_runs(app_session_factory, tenant_id, term_id)
    assert len(runs) == 1  # a run aberta foi consumida, não duplicada
    assert run is not None and run.id == runs[0].id
    assert runs[0].finished_at is not None and runs[0].new_count == 1
