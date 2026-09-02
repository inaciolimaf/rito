"""Checagem leve de saúde do DJEN (spec 049, regra 5) — reaproveita o endpoint
real de busca com uma janela de um dia e `per_page=1`; o DJEN não tem um
endpoint de ping dedicado. Não é importado por nenhum teste (mesmo padrão de
`app/workers/djen_sync.py`) — a regra de negócio fica em
`IntegrationHealthService`, exercitada com um fake do Protocol.
"""

import time
from datetime import UTC, datetime

from app.domain.integrations.service import HealthCheckResult
from app.integrations.djen.client import DjenApiError, DjenClient, DjenConfigError


class DjenHealthChecker:
    integration = "djen"

    def __init__(self, client: DjenClient) -> None:
        self._client = client

    async def check(self) -> HealthCheckResult:
        started = time.monotonic()
        # UTC explícito, e não o relógio do escritório (spec 114): esta é uma sonda
        # contra a API nacional do DJEN, não uma consulta de tenant. Não há escritório
        # aqui — há um probe que precisa de uma data válida qualquer, e a do servidor
        # em UTC é a única defensável quando não existe conta para perguntar.
        today = datetime.now(UTC).date()
        try:
            await self._client.fetch_communications(
                availability_start=today, availability_end=today, per_page=1
            )
        except (DjenApiError, DjenConfigError) as exc:
            return HealthCheckResult(is_healthy=False, latency_ms=None, detail=str(exc))
        latency_ms = int((time.monotonic() - started) * 1000)
        return HealthCheckResult(is_healthy=True, latency_ms=latency_ms, detail=None)
