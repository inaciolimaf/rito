"""Checagem leve de saúde do DataJud (spec 049, regra 5) — a API pública não tem
endpoint de ping; usa uma busca por um número de processo inexistente num
alias fixo (TJSP) só pra confirmar que a API responde. Não é importado por
nenhum teste (mesmo padrão de `app/workers/datajud_sync.py`).
"""

import time

from app.domain.integrations.service import HealthCheckResult
from app.integrations.datajud.client import DatajudApiError, DatajudClient, DatajudConfigError

_PING_ALIAS = "api_publica_tjsp"
_PING_PROCESS_NUMBER = "00000000000000000000"


class DatajudHealthChecker:
    integration = "datajud"

    def __init__(self, client: DatajudClient) -> None:
        self._client = client

    async def check(self) -> HealthCheckResult:
        started = time.monotonic()
        try:
            await self._client.search_by_process_number(
                alias=_PING_ALIAS, process_number=_PING_PROCESS_NUMBER
            )
        except (DatajudApiError, DatajudConfigError) as exc:
            return HealthCheckResult(is_healthy=False, latency_ms=None, detail=str(exc))
        latency_ms = int((time.monotonic() - started) * 1000)
        return HealthCheckResult(is_healthy=True, latency_ms=latency_ms, detail=None)
