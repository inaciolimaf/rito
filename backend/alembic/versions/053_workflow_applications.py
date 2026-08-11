"""workflow_applications + workflow_suppressions (spec 053 — CRM: workflow ao mover)

Revision ID: 053_workflow_applications
Revises: 052_stagnation
Create Date: 2026-08-11

`workflow_suppressions` não tem PK surrogate na spec (PK composta lawsuit_id+stage_id) —
aqui ganha o `id` UUID padrão de `Base` (toda tabela do projeto tem, sem exceção) com um
UNIQUE(lawsuit_id, stage_id) fazendo o mesmo papel de "1 supressão por par". Mantém
`BaseRepository`/RLS/o resto da infra funcionando sem caso especial.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls

revision: str = "053_workflow_applications"
down_revision: str | None = "052_stagnation"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "workflow_applications",
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
            "workflow_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workflows.id"),
            nullable=False,
        ),
        sa.Column(
            "lawsuit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lawsuits.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "stage_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stages.id"), nullable=True
        ),
        sa.Column(
            "applied_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "posts_created",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "applied_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_wf_app_lawsuit", "workflow_applications", ["lawsuit_id", sa.text("applied_at DESC")]
    )
    enable_rls("workflow_applications")

    op.create_table(
        "workflow_suppressions",
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
            "lawsuit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lawsuits.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "stage_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("stages.id"), nullable=False
        ),
        sa.UniqueConstraint(
            "lawsuit_id", "stage_id", name="uq_workflow_suppressions_lawsuit_stage"
        ),
    )
    enable_rls("workflow_suppressions")


def downgrade() -> None:
    op.drop_table("workflow_suppressions")
    op.drop_table("workflow_applications")
