"""Montagem do provider (spec 081).

Em `app_env=test` o transporte é o de fixtures gravadas em `tests/fixtures/llm/`
(regra 12) — nenhuma chamada de LLM real acontece em teste, nem por engano: o
`FixtureTransport` falha explicitamente quando a fixture não existe, em vez de cair
na rede.
"""

from pathlib import Path

import httpx
from redis.asyncio import Redis

from app.core.config import get_settings
from app.integrations.http.audit import AuditSink
from app.integrations.http.client import ResilientHttpClient
from app.integrations.http.fixtures import FixtureTransport
from app.integrations.http.types import HostPolicy
from app.integrations.openrouter.client import COMPLETION_TIMEOUT_S, OpenRouterProvider


def create_llm_provider(
    *, redis: Redis | None = None, audit: AuditSink | None = None
) -> OpenRouterProvider:
    settings = get_settings()
    transport: httpx.AsyncBaseTransport | None = None
    if settings.app_env == "test":
        transport = FixtureTransport(Path(settings.llm_fixtures_dir), record=settings.http_record)
    http = ResilientHttpClient(
        transport=transport,
        redis=redis,
        audit=audit,
        policies={
            "openrouter.ai": HostPolicy(
                timeout_s=COMPLETION_TIMEOUT_S,  # regra 9
                # Erro de LLM raramente melhora na retentativa imediata, e cada
                # tentativa custa dinheiro: uma repetição, não três.
                max_retries=1,
                rate_limit_per_minute=(
                    settings.openrouter_rate_limit_per_minute if redis is not None else None
                ),
            )
        },
    )
    return OpenRouterProvider(
        http=http,
        streaming_http=http,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        site_url=settings.openrouter_site_url,
        app_name=settings.openrouter_app_name,
    )
