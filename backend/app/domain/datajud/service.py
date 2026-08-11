"""Orquestração DataJud (spec 046, §7): resolve o alias do tribunal, consulta o
client, aplica o descarte de sigilo (regra 6) e o aviso de código de movimento
desconhecido (regra 7) — a leitura do banco que o parser puro não pode fazer.

A sincronização de andamentos (persistir `ParsedProcess` em `lawsuit_movements`,
incremental por `dataHoraUltimaAtualizacao`) é da spec 047, que consome
`fetch_process_status` — `fetch_process` (046) continua igual para quem só
precisa da capa, sem distinguir "sigiloso" de "não encontrado".
"""

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.courts.models import Court
from app.domain.courts.repository import CnjMovementCodeRepository, CourtRepository
from app.domain.datajud.exceptions import CourtNotSupportedError
from app.domain.integration_alerts.models import IntegrationAlert
from app.domain.integration_alerts.repository import IntegrationAlertRepository
from app.integrations.datajud.client import DatajudClient, DatajudUnauthorizedError
from app.integrations.datajud.parser import ParsedProcess

logger = logging.getLogger("rito.datajud")

_UNAUTHORIZED_MESSAGE = (
    "Chave pública do DataJud inválida ou rotacionada. Gere uma nova em "
    "https://datajud-wiki.cnj.jus.br/api-publica/acesso/ e atualize DATAJUD_API_KEY."
)


@dataclass
class ProcessFetchStatus:
    """Resultado completo de uma consulta (spec 047) — distingue "sigiloso" de
    "não encontrado", que `fetch_process` (046) colapsa em `None` porque quem só
    quer a capa não precisa da diferença."""

    process: ParsedProcess | None
    sealed: bool = False


class DatajudService:
    def __init__(self, session: AsyncSession, client: DatajudClient) -> None:
        self.session = session
        self.client = client
        self.courts = CourtRepository(session)
        self.movement_codes = CnjMovementCodeRepository(session)
        self.alerts = IntegrationAlertRepository(session)

    async def fetch_process(self, court: Court, process_number: str) -> ParsedProcess | None:
        """Devolve `None` quando não há hit ou o processo é sigiloso (regra 6) —
        os dois casos não são erro, só "nada para persistir"."""
        status = await self.fetch_process_status(court, process_number)
        return status.process

    async def fetch_process_status(self, court: Court, process_number: str) -> ProcessFetchStatus:
        if not court.datajud_alias:
            raise CourtNotSupportedError(court.code)  # regra 4 da 046

        try:
            results = await self.client.search_by_process_number(
                alias=court.datajud_alias, process_number=process_number
            )
        except DatajudUnauthorizedError:
            await self._create_key_rotated_alert()  # regra 3 da 046
            raise

        if not results:
            return ProcessFetchStatus(process=None, sealed=False)

        process = results[0]
        if process.secrecy_level > 0:
            return ProcessFetchStatus(process=None, sealed=True)  # regra 6 da 046

        await self._warn_unknown_movement_codes(process)
        return ProcessFetchStatus(process=process, sealed=False)

    async def _create_key_rotated_alert(self) -> None:
        # Regra 3: tenant_id nulo — DATAJUD_API_KEY é config global, o problema é
        # de todo mundo, não de um tenant específico. Dedup (spec 050, alvo 2 — achado
        # da auditoria de caos "401 permanente"): sem isso, cada processo do lote que
        # bate 401 criava um alerta novo, inundando o banner/painel com duplicatas.
        existing = await self.alerts.get_open_by_code(integration="datajud", code="api_key_rotated")
        if existing is not None:
            return
        await self.alerts.create(
            IntegrationAlert(
                tenant_id=None,
                integration="datajud",
                severity="critical",
                code="api_key_rotated",
                message=_UNAUTHORIZED_MESSAGE,
            )
        )

    async def _warn_unknown_movement_codes(self, process: ParsedProcess) -> None:
        codes = {movement.code for movement in process.movements}
        if not codes:
            return
        known = await self.movement_codes.existing_codes(codes)
        for code in sorted(codes - known):
            logger.warning(
                "datajud: código de movimento desconhecido %s no processo %s — "
                "atualize app/domain/courts/movement_codes_seed.py",
                code,
                process.process_number,
            )
