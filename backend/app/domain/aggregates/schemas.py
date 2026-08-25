"""Contratos da API de agregados (spec 078 §5) + o envelope `meta` que toda resposta
de BI passa a carregar."""

from datetime import datetime

from pydantic import BaseModel


class AggregateMeta(BaseModel):
    """Defasagem do dado servido (§5). `computed_at` None = a view nunca foi
    refrescada pelo orquestrador (dado do CREATE MATERIALIZED VIEW) — tratado como
    defasado por definição (`is_stale` true, regra 6: defasagem infinita > 2× o
    intervalo)."""

    computed_at: datetime | None
    staleness_seconds: int | None
    is_stale: bool


class AggregateStatusItem(BaseModel):
    """Uma linha do `GET /aggregates/status` — o registry + descrição (do catálogo
    `MATERIALIZED_VIEWS`) + a defasagem derivada (regra 6)."""

    name: str
    description: str
    refresh_interval_seconds: int
    invalidate_on: list[str]
    last_refresh_at: datetime | None
    last_refresh_duration_ms: int | None
    last_error: str | None
    is_enabled: bool
    computed_at: datetime | None
    staleness_seconds: int | None
    is_stale: bool


class AggregateStatusResponse(BaseModel):
    items: list[AggregateStatusItem]
