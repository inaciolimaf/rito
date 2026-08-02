"""lawsuits

Revision ID: 022_lawsuits
Revises: 021_courts_systems
Create Date: 2026-08-02

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "022_lawsuits"
down_revision: str | None = "021_courts_systems"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "lawsuits",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "lawsuit_type_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lawsuit_types.id"),
            nullable=False,
        ),
        sa.Column(
            "stage_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stages.id"), nullable=False
        ),
        sa.Column("court_id", sa.SmallInteger(), sa.ForeignKey("courts.id"), nullable=True),
        sa.Column(
            "court_system_id", sa.SmallInteger(), sa.ForeignKey("court_systems.id"), nullable=True
        ),
        sa.Column("process_number", sa.Text(), nullable=True),
        sa.Column("protocol_number", sa.Text(), nullable=True),
        sa.Column("originating_process", sa.Text(), nullable=True),
        sa.Column("folder", sa.Text(), nullable=True),
        sa.Column("filing_year", sa.SmallInteger(), nullable=True),
        sa.Column("judiciary", sa.Text(), nullable=True),
        sa.Column("county", sa.Text(), nullable=True),
        sa.Column("court_division", sa.Text(), nullable=True),
        sa.Column("process_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "folder IS NULL OR length(folder) <= 30", name="ck_lawsuits_folder_length"
        ),
    )
    op.create_index("ix_lawsuits_user", "lawsuits", ["tenant_id", "user_id"])
    op.create_index("ix_lawsuits_stage", "lawsuits", ["tenant_id", "stage_id"])
    op.create_index("ix_lawsuits_type", "lawsuits", ["tenant_id", "lawsuit_type_id"])
    op.execute(
        "CREATE INDEX ix_lawsuits_number ON lawsuits (tenant_id, process_number) "
        "WHERE process_number IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_lawsuits_folder ON lawsuits (tenant_id, folder) WHERE folder IS NOT NULL"
    )
    for statement in enable_rls_statements("lawsuits"):
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("lawsuits")
