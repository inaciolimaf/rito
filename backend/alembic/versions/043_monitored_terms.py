"""monitored_terms e term_sync_runs (termos monitorados do DJEN)

Revision ID: 043_monitored_terms
Revises: 042_publications
Create Date: 2026-08-10

Spec 043, §4: o que o escritório vigia (OAB/CPF/CNPJ) e o histórico de execuções
de sincronização. Detalhe de modelagem: a UNIQUE inclui `oab_state`, que é nulo
para CPF/CNPJ — sem NULLS NOT DISTINCT o Postgres trataria os nulos como
distintos e dois CPFs iguais não colidiriam (regra 3).

`ix_terms_due` é o índice do agendador (044): parcial em `is_active AND
status <> 'PAUSADO'` — pausar tira o termo da varredura sem apagar nada (regra 7).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls

revision: str = "043_monitored_terms"
down_revision: str | None = "042_publications"
branch_labels: str | None = None
depends_on: str | None = None

# Sem create_type=False aqui: `create_table` emite o CREATE TYPE dos enums sozinho
# (padrão das migrations 023/031 — chamada manual daria DuplicateObjectError). O
# create_type=False fica no MODEL (app/domain/monitored_terms/models.py).
term_kind = postgresql.ENUM("OAB", "CPF", "CNPJ", name="term_kind")
term_status = postgresql.ENUM(
    "PENDENTE", "SINCRONIZANDO", "ATIVO", "FALHA", "PAUSADO", name="term_status"
)


def upgrade() -> None:
    op.create_table(
        "monitored_terms",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("kind", term_kind, nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "oab_state",
            sa.CHAR(2),
            sa.ForeignKey("states.code"),
            nullable=True,
        ),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "status",
            term_status,
            nullable=False,
            server_default="PENDENTE",
        ),
        sa.Column("status_message", sa.Text(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("backfill_from", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "kind",
            "value",
            "oab_state",
            name="uq_monitored_terms_term",
            postgresql_nulls_not_distinct=True,
        ),
        sa.CheckConstraint(
            "kind <> 'OAB' OR oab_state IS NOT NULL", name="ck_monitored_terms_oab_state"
        ),
    )
    op.create_index(
        "ix_terms_due",
        "monitored_terms",
        ["next_sync_at"],
        postgresql_where=sa.text("is_active AND status <> 'PAUSADO'"),
    )

    op.create_table(
        "term_sync_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "term_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("monitored_terms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("found_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_sync_runs_term",
        "term_sync_runs",
        ["term_id", sa.text("started_at DESC")],
    )

    for table in ("monitored_terms", "term_sync_runs"):
        enable_rls(table)


def downgrade() -> None:
    op.drop_table("term_sync_runs")
    op.drop_table("monitored_terms")
    op.execute("DROP TYPE term_status")
    op.execute("DROP TYPE term_kind")
