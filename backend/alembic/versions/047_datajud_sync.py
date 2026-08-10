"""andamentos via DataJud (spec 047)

Revision ID: 047_datajud_sync
Revises: 046_datajud
Create Date: 2026-08-10

Spec 047, §4: campos de controle da sincronização e enriquecimento de capa em
`lawsuits`, mais `lawsuit_subjects` (assuntos do CNJ). `datajud_not_found_count`
é o mecanismo de pausa (regra 5) — sem coluna de status dedicada: ao chegar em 5
(ou imediatamente em caso de sigilo, regra 4 — Descobertas), o processo sai da
fila de `ix_lawsuits_datajud_due` sozinho, pela condição do índice.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls

revision: str = "047_datajud_sync"
down_revision: str | None = "046_datajud"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("lawsuits", sa.Column("datajud_last_sync_at", sa.DateTime(timezone=True)))
    op.add_column("lawsuits", sa.Column("datajud_last_update", sa.DateTime(timezone=True)))
    op.add_column(
        "lawsuits",
        sa.Column("datajud_not_found_count", sa.SmallInteger(), nullable=False, server_default="0"),
    )
    op.add_column("lawsuits", sa.Column("judging_organ", sa.Text(), nullable=True))
    op.add_column("lawsuits", sa.Column("filing_date", sa.Date(), nullable=True))
    op.add_column("lawsuits", sa.Column("cnj_class_code", sa.Integer(), nullable=True))
    op.add_column("lawsuits", sa.Column("cnj_class_name", sa.Text(), nullable=True))

    op.execute(
        "CREATE INDEX ix_lawsuits_datajud_due ON lawsuits "
        "(tenant_id, datajud_last_sync_at NULLS FIRST) "
        "WHERE process_number IS NOT NULL AND NOT is_archived AND datajud_not_found_count < 5"
    )

    op.create_table(
        "lawsuit_subjects",
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
            "lawsuit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lawsuits.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.UniqueConstraint("lawsuit_id", "code", name="uq_lawsuit_subjects_code"),
    )
    enable_rls("lawsuit_subjects")


def downgrade() -> None:
    op.drop_table("lawsuit_subjects")
    op.execute("DROP INDEX IF EXISTS ix_lawsuits_datajud_due")
    op.drop_column("lawsuits", "cnj_class_name")
    op.drop_column("lawsuits", "cnj_class_code")
    op.drop_column("lawsuits", "filing_date")
    op.drop_column("lawsuits", "judging_organ")
    op.drop_column("lawsuits", "datajud_not_found_count")
    op.drop_column("lawsuits", "datajud_last_update")
    op.drop_column("lawsuits", "datajud_last_sync_at")
