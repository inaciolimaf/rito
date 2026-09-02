"""Modelos do registro central de agregados (spec 078 §4).

Tabelas GLOBAIS, sem `tenant_id` e sem RLS — mesmo padrão de `integration_health`
(spec 049): as views materializadas são compartilhadas entre tenants e o isolamento
acontece na leitura, pelas views barreira. Por isso nenhum dos dois modelos usa
`TenantMixin`.
"""

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import CRIADO_EM, Base


class AggregateRegistry(Base):
    """Uma linha por view materializada (regra 1: toda matview está aqui — coberto
    pelo teste meta de cobertura). Carrega o estado do último refresh para a API
    expor a defasagem (`meta` das respostas de BI, §5). `name` é UNIQUE (a spec
    escreve PRIMARY KEY; a Base da casa já traz o `id` UUID — a unicidade de `name`
    é o que o FK do log e o refresh usam)."""

    __tablename__ = "aggregate_registry"

    name: Mapped[str] = mapped_column(Text, unique=True)
    refresh_interval_seconds: Mapped[int] = mapped_column(Integer)
    invalidate_on: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    last_refresh_at: Mapped[datetime | None] = mapped_column(default=None)
    last_refresh_duration_ms: Mapped[int | None] = mapped_column(default=None)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    is_enabled: Mapped[bool] = mapped_column(server_default=func.true())


class AggregateRefreshLog(Base):
    """Histórico de refreshes (um por execução, sucesso ou falha) — regra 9 usa a
    duração para alertar refresh lento; a falha fica registrada aqui e em
    `aggregate_registry.last_error`. O `id` UUID vem da Base (convenção da casa)."""

    __tablename__ = "aggregate_refresh_log"

    name: Mapped[str] = mapped_column(Text, ForeignKey("aggregate_registry.name"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    rows_affected: Mapped[int | None] = mapped_column(BigInteger, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
