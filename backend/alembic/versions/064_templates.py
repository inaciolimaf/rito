"""templates (spec 064 — Modelos: biblioteca)

Revision ID: 064_templates
Revises: 063_documents
Create Date: 2026-08-13

`deleted_at` é a lixeira (regra 3): a linha nunca é apagada, só marcada. O índice
parcial (`WHERE deleted_at IS NULL`) é o mesmo raciocínio de `ix_document_folders`
(spec 063) — a listagem normal (a mais frequente) nunca varre linha da lixeira.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "064_templates"
down_revision: str | None = "063_documents"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("CREATE TYPE template_type AS ENUM ('CONTRATO', 'PETICAO', 'RECURSO', 'DOCUMENTO')")

    op.create_table(
        "templates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "type",
            postgresql.ENUM(
                "CONTRATO",
                "PETICAO",
                "RECURSO",
                "DOCUMENTO",
                name="template_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_templates_tenant_type",
        "templates",
        ["tenant_id", "type"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    for statement in enable_rls_statements("templates"):
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("templates")
    op.execute("DROP TYPE template_type")
