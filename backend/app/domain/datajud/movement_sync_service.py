"""Sincronização de andamentos via DataJud (spec 047, §5).

Unidade de trabalho: um processo (`sync_lawsuit`). `sync_due` percorre a fila
(`ix_lawsuits_datajud_due`) em lote, isolando falha por processo (regra 11) —
mesmo padrão de `TermSyncService.sync_terms` (spec 044). Nenhuma chamada de
rede aqui: tudo passa por `DatajudService`/`DatajudClient` (spec 046), que já
carregam a resiliência da camada 041.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.locks import SyncLock
from app.domain.courts.models import Court
from app.domain.courts.repository import CourtRepository
from app.domain.datajud.exceptions import LawsuitSyncInProgressError
from app.domain.datajud.service import DatajudService
from app.domain.integration_alerts.models import IntegrationAlert
from app.domain.integration_alerts.repository import IntegrationAlertRepository
from app.domain.lawsuits.cnj import CNJValidationError, infer_court_code, parse_cnj
from app.domain.lawsuits.models import Lawsuit, LawsuitMovement, LawsuitSubject, MovementOrigin
from app.domain.lawsuits.repository import (
    DATAJUD_NOT_FOUND_PAUSE_THRESHOLD,
    LawsuitMovementRepository,
    LawsuitRepository,
    LawsuitSubjectRepository,
)
from app.integrations.datajud.parser import ParsedMovement, ParsedProcess

logger = logging.getLogger("rito.datajud")

SYNC_LOCK_TTL_SECONDS = 120


def sync_lock_key(lawsuit_id: uuid.UUID) -> str:
    return f"rito:datajud_sync:{lawsuit_id}"


@dataclass
class LawsuitSyncResult:
    lawsuit_id: uuid.UUID
    status: str  # 'synced' | 'unchanged' | 'not_found' | 'sealed' | 'no_court' | 'error'
    new_movements: int = 0
    error: str | None = None


def _movement_external_id(movement: ParsedMovement) -> str:
    """A API não devolve um id por movimento (glossário oficial só tem
    codigo/nome/dataHora/complementos/orgaoJulgador — verificado na spec 046) —
    a chave de dedupe (regra 2) é a combinação que identifica a ocorrência."""
    occurred = movement.occurred_at.isoformat() if movement.occurred_at else ""
    return f"{movement.code}:{occurred}:{movement.organ_code or ''}"


def _format_complements(movement: ParsedMovement) -> str | None:
    parts = [
        complement.name or complement.description
        for complement in movement.complements
        if complement.name or complement.description
    ]
    return "; ".join(part for part in parts if part) or None


class MovementSyncService:
    def __init__(
        self, session: AsyncSession, tenant_id: uuid.UUID, datajud: DatajudService
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.datajud = datajud
        self.lawsuits = LawsuitRepository(session)
        self.movements = LawsuitMovementRepository(session)
        self.subjects = LawsuitSubjectRepository(session)
        self.courts = CourtRepository(session)
        self.alerts = IntegrationAlertRepository(session)

    async def resolve_court(self, lawsuit: Lawsuit) -> Court | None:
        """Regra do §5: alias pelo tribunal já vinculado ao processo, ou inferido
        pelo número CNJ (spec 025) quando `court_id` está vazio."""
        if lawsuit.court_id is not None:
            return await self.session.get(Court, lawsuit.court_id)
        if not lawsuit.process_number:
            return None
        try:
            parsed_number = parse_cnj(lawsuit.process_number)
        except CNJValidationError:
            return None
        code = infer_court_code(parsed_number)
        if code is None:
            return None
        return await self.courts.get_by_code(code)

    async def sync_lawsuit_locked(
        self, lawsuit: Lawsuit, lock: SyncLock, *, ttl_seconds: int = SYNC_LOCK_TTL_SECONDS
    ) -> LawsuitSyncResult:
        """Regra 10: sincronização manual concorrente do MESMO processo → o
        chamador (router) traduz `LawsuitSyncInProgressError` em 409."""
        key = sync_lock_key(lawsuit.id)
        if not await lock.acquire(key, ttl_seconds=ttl_seconds):
            raise LawsuitSyncInProgressError
        try:
            return await self.sync_lawsuit(lawsuit)
        finally:
            await lock.release(key)

    async def sync_due(self, *, batch_size: int) -> list[LawsuitSyncResult]:
        """Regra 9: a fila é processada em lotes — `batch_size` é o teto por chamada,
        o rate limit em si mora na camada 041, por host."""
        lawsuits = await self.lawsuits.list_due_for_datajud_sync(limit=batch_size)
        results: list[LawsuitSyncResult] = []
        for lawsuit in lawsuits:
            try:
                result = await self.sync_lawsuit(lawsuit)
            except Exception as exc:  # regra 11: um processo ruim não trava o lote
                logger.exception("datajud_sync: falha inesperada no processo %s", lawsuit.id)
                result = LawsuitSyncResult(lawsuit.id, "error", error=str(exc))
            results.append(result)
        return results

    async def sync_lawsuit(self, lawsuit: Lawsuit) -> LawsuitSyncResult:
        court = await self.resolve_court(lawsuit)
        if court is None or not court.datajud_alias:
            return LawsuitSyncResult(lawsuit.id, "no_court")

        assert lawsuit.process_number is not None  # regra 1: só entra na fila com número
        now = datetime.now(UTC)
        status = await self.datajud.fetch_process_status(court, lawsuit.process_number)

        if status.sealed:
            # Regra 4: nada é persistido; "não sincronizável" = sai da fila de vez,
            # sem esperar 5 tentativas (o sigilo não muda de uma consulta pra outra).
            lawsuit.datajud_not_found_count = DATAJUD_NOT_FOUND_PAUSE_THRESHOLD
            lawsuit.datajud_last_sync_at = now
            await self.session.flush()
            return LawsuitSyncResult(lawsuit.id, "sealed")

        if status.process is None:
            lawsuit.datajud_not_found_count += 1
            lawsuit.datajud_last_sync_at = now
            if lawsuit.datajud_not_found_count == DATAJUD_NOT_FOUND_PAUSE_THRESHOLD:
                await self._create_not_found_alert(lawsuit)  # regra 5
            await self.session.flush()
            return LawsuitSyncResult(lawsuit.id, "not_found")

        process = status.process
        lawsuit.datajud_not_found_count = 0  # regra 5: sucesso reseta a sequência

        # Regra 3: sem novidade no CNJ, termina sem escrever movimento/capa nenhum.
        unchanged = (
            lawsuit.datajud_last_update is not None
            and process.last_updated_at is not None
            and process.last_updated_at <= lawsuit.datajud_last_update
        )
        new_movements = 0
        if not unchanged:
            new_movements = await self._persist_movements(lawsuit, process)
            await self._persist_subjects(lawsuit, process)
            self._enrich_cover(lawsuit, process)
            if process.last_updated_at is not None:
                lawsuit.datajud_last_update = process.last_updated_at

        lawsuit.datajud_last_sync_at = now
        await self.session.flush()
        status_label = "synced" if new_movements else "unchanged"
        return LawsuitSyncResult(lawsuit.id, status_label, new_movements=new_movements)

    async def _persist_movements(self, lawsuit: Lawsuit, process: ParsedProcess) -> int:
        new_count = 0
        for movement in process.movements:
            if movement.occurred_at is None:
                continue
            if (
                lawsuit.datajud_last_update is not None
                and movement.occurred_at <= lawsuit.datajud_last_update
            ):
                continue  # regra 3: só o que é mais novo que o último processado
            external_id = _movement_external_id(movement)
            existing = await self.movements.find_by_external_id(lawsuit.id, external_id)
            if existing is not None:
                continue  # regra 2: dedup — defesa extra além do filtro de data acima
            self.session.add(
                LawsuitMovement(
                    tenant_id=self.tenant_id,
                    lawsuit_id=lawsuit.id,
                    origin=MovementOrigin.TRIBUNAL,  # regra 6: imutável na UI (026)
                    occurred_at=movement.occurred_at,
                    title=movement.name,
                    body=_format_complements(movement),
                    header=movement.organ_name,
                    external_code=movement.code,
                    external_id=external_id,
                )
            )
            new_count += 1
        if new_count:
            # last_movement_at é a trigger trg_movements_last_movement (027) — nunca
            # escrito na mão (regra 7); o flush só garante o INSERT pra ela disparar.
            await self.session.flush()
        return new_count

    async def _persist_subjects(self, lawsuit: Lawsuit, process: ParsedProcess) -> None:
        existing = await self.subjects.existing_codes(lawsuit.id)
        for subject in process.subjects:
            if subject.code is None or subject.code in existing:
                continue
            self.session.add(
                LawsuitSubject(
                    tenant_id=self.tenant_id,
                    lawsuit_id=lawsuit.id,
                    code=subject.code,
                    name=subject.name or "",
                )
            )
            existing.add(subject.code)

    def _enrich_cover(self, lawsuit: Lawsuit, process: ParsedProcess) -> None:
        """Regra 8: só escreve campo vazio — dado digitado pelo usuário vence."""
        if lawsuit.judging_organ is None and process.organ_name:
            lawsuit.judging_organ = process.organ_name
        if lawsuit.filing_date is None and process.filed_at is not None:
            # Regra 12: filing_date (ajuizamento, do CNJ) NUNCA toca process_date
            # (requerimento, do usuário) — são campos diferentes.
            lawsuit.filing_date = process.filed_at.date()
        if lawsuit.cnj_class_code is None and process.class_code is not None:
            lawsuit.cnj_class_code = process.class_code
        if lawsuit.cnj_class_name is None and process.class_name:
            lawsuit.cnj_class_name = process.class_name

    async def _create_not_found_alert(self, lawsuit: Lawsuit) -> None:
        await self.alerts.create(
            IntegrationAlert(
                tenant_id=lawsuit.tenant_id,  # alerta de TENANT — não é config global
                integration="datajud",
                severity="warning",
                code="process_not_found",
                message=(
                    f"Processo {lawsuit.process_number} não encontrado no DataJud "
                    f"{DATAJUD_NOT_FOUND_PAUSE_THRESHOLD} vezes seguidas — confira o "
                    "número ou se o tribunal tem cobertura na API pública."
                ),
            )
        )
