"""registry central de agregados (views materializadas)

Revision ID: 078_aggregate_registry
Revises: 077_bi_costs
Create Date: 2026-08-25

Spec 078 §4: as views materializadas (039/059/071/073/074/075/076/077) viravam
infraestrutura solta — cada worker com seu beat, sem registro do último refresh nem
histórico de falhas. Esta migration cria o registro global (sem tenant: as views são
compartilhadas e filtradas por `tenant_id` na leitura, via views barreira) e o log de
refreshes, já semeando as oito views existentes com os intervalos da regra 2
(BI 8 h · produtividade/agilidade 15 min · saldo diário 10 min) e os eventos de
invalidação da regra 5.

Sem RLS propositalmente — mesmo padrão de `integration_health` (spec 049): tabela
global de telemetria. Os grants de rito_app vêm dos DEFAULT PRIVILEGES da migration
003. O mapeamento evento → views que o worker usa para agendar refresh
(`app/workers/aggregates.py::EVENT_TO_VIEWS`) espelha a coluna `invalidate_on` — se um
mudar, o outro muda junto.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "078_aggregate_registry"
down_revision: str | None = "077_bi_costs"
branch_labels: str | None = None
depends_on: str | None = None

# (name, refresh_interval_seconds, invalidate_on) — espelha EVENT_TO_VIEWS de
# app/workers/aggregates.py. Intervalos da regra 2: BI 8 h (28800 s), produtividade/
# agilidade 15 min (900 s), saldo diário 10 min (600 s).
_SEED: list[tuple[str, int, list[str]]] = [
    ("user_monthly_scores", 900, ["task.completed"]),
    ("account_daily_balances", 600, ["transaction.paid"]),
    ("agility_daily", 900, ["task.completed"]),
    ("timesheet_daily", 900, []),
    ("bi_pipeline_monthly", 28800, ["lawsuit.closed", "lawsuit.archived"]),
    ("bi_vintage", 28800, ["lawsuit.closed", "lawsuit.archived"]),
    ("bi_lawsuit_cycles", 28800, ["lawsuit.closed", "lawsuit.archived", "transaction.paid"]),
    ("bi_cost_allocation", 28800, ["task.completed", "transaction.paid"]),
]


def upgrade() -> None:
    op.create_table(
        "aggregate_registry",
        # Convenção da casa (app/core/models.py: toda tabela herda `id` UUID da
        # Base) — a spec escreve `name TEXT PRIMARY KEY`; aqui `name` fica UNIQUE,
        # que é o que o FK do log e o refresh precisam.
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("refresh_interval_seconds", sa.Integer(), nullable=False),
        sa.Column(
            "invalidate_on",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("last_refresh_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_refresh_duration_ms", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "aggregate_refresh_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "name",
            sa.Text(),
            sa.ForeignKey("aggregate_registry.name"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rows_affected", sa.BigInteger(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_refresh_log",
        "aggregate_refresh_log",
        ["name", sa.text("started_at DESC")],
    )

    registry = sa.table(
        "aggregate_registry",
        sa.column("name", sa.Text()),
        sa.column("refresh_interval_seconds", sa.Integer()),
        sa.column("invalidate_on", postgresql.ARRAY(sa.Text())),
    )
    op.bulk_insert(
        registry,
        [
            {
                "name": name,
                "refresh_interval_seconds": interval,
                "invalidate_on": events,
            }
            for name, interval, events in _SEED
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_log", table_name="aggregate_refresh_log")
    op.drop_table("aggregate_refresh_log")
    op.drop_table("aggregate_registry")
