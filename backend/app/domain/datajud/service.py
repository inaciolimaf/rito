"""Orquestração DataJud (spec 046, §7): resolve o alias do tribunal, consulta o
client, aplica o descarte de sigilo (regra 6) e o aviso de código de movimento
desconhecido (regra 7) — a leitura do banco que o parser puro não pode fazer.

A sincronização de andamentos (persistir `ParsedProcess` em `lawsuit_movements`,
incremental por `dataHoraUltimaAtualizacao`) é da spec 047 — aqui a unidade de
trabalho é uma única consulta de capa processual.
"""

import logging

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
        if not court.datajud_alias:
            raise CourtNotSupportedError(court.code)  # regra 4

        try:
            results = await self.client.search_by_process_number(
                alias=court.datajud_alias, process_number=process_number
            )
        except DatajudUnauthorizedError:
            await self._create_key_rotated_alert()  # regra 3
            raise

        if not results:
            return None

        process = results[0]
        if process.secrecy_level > 0:
            return None  # regra 6: segredo de justiça, descartado sem persistir

        await self._warn_unknown_movement_codes(process)
        return process

    async def _create_key_rotated_alert(self) -> None:
        # Regra 3: tenant_id nulo — DATAJUD_API_KEY é config global, o problema é
        # de todo mundo, não de um tenant específico.
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
