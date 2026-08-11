"""Checagem leve de saúde do DJEN (spec 049, regra 5) — reaproveita o endpoint
real de busca com uma janela de um dia e `per_page=1`; o DJEN não tem um
endpoint de ping dedicado. Não é importado por nenhum teste (mesmo padrão de
`app/workers/djen_sync.py`) — a regra de negócio fica em
`IntegrationHealthService`, exercitada com um fake do Protocol.
"""

import time
from datetime import date

from app.domain.integrations.service import HealthCheckResult
from app.integrations.djen.client import DjenApiError, DjenClient, DjenConfigError


class DjenHealthChecker:
    integration = "djen"

    def __init__(self, client: DjenClient) -> None:
        self._client = client

    async def check(self) -> HealthCheckResult:
        started = time.monotonic()
        today = date.today()
        try:
            await self._client.fetch_communications(
                availability_start=today, availability_end=today, per_page=1
            )
        except (DjenApiError, DjenConfigError) as exc:
            return HealthCheckResult(is_healthy=False, latency_ms=None, detail=str(exc))
        latency_ms = int((time.monotonic() - started) * 1000)
        return HealthCheckResult(is_healthy=True, latency_ms=latency_ms, detail=None)
