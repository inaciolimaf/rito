"""accounts.plan + document_folders + documents (spec 063 — Documentos e nuvem)

Revision ID: 063_documents
Revises: 061_dunning
Create Date: 2026-08-13

`plan` entra em `accounts` (spec 011) porque é dali que a nuvem de documentos lê a
quota (regra 5/6) — não faz sentido uma tabela de billing só pra isso quando o Rito
não tem billing (spec 063 §3). `ON DELETE CASCADE` em `parent_folder_id` e
`documents.folder_id` é o que faz a regra 4 (excluir pasta remove subpasta e
documento) funcionar sem o service ter que apagar linha por linha — só os objetos do
bucket (que o banco não sabe apagar) ficam por conta do service.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "063_documents"
down_revision: str | None = "061_dunning"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE account_plan AS ENUM " "('ESSENCIAL', 'BANCA_JURIDICA', 'BANCA_MAX', 'ELITE')"
    )
    op.add_column(
        "accounts",
        sa.Column(
            "plan",
            postgresql.ENUM(
                "ESSENCIAL",
                "BANCA_JURIDICA",
                "BANCA_MAX",
                "ELITE",
                name="account_plan",
                create_type=False,
            ),
            nullable=False,
            server_default="ESSENCIAL",
        ),
    )

    op.execute("CREATE TYPE document_scope_type AS ENUM ('CUSTOMER', 'LAWSUIT')")

    op.create_table(
        "document_folders",
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
            "scope_type",
            postgresql.ENUM("CUSTOMER", "LAWSUIT", name="document_scope_type", create_type=False),
            nullable=False,
        ),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "parent_folder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_folders.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "scope_type",
            "scope_id",
            "parent_folder_id",
            "name",
            name="uq_document_folders_location_name",
        ),
    )
    for statement in enable_rls_statements("document_folders"):
        op.execute(statement)

    op.create_table(
        "documents",
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
            "scope_type",
            postgresql.ENUM("CUSTOMER", "LAWSUIT", name="document_scope_type", create_type=False),
            nullable=False,
        ),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "folder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_folders.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("size_bytes >= 0 AND size_bytes <= 52428800", name="ck_documents_size"),
    )
    op.create_index(
        "ix_documents_scope", "documents", ["tenant_id", "scope_type", "scope_id", "folder_id"]
    )
    for statement in enable_rls_statements("documents"):
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("documents")
    op.drop_table("document_folders")
    op.execute("DROP TYPE document_scope_type")
    op.drop_column("accounts", "plan")
    op.execute("DROP TYPE account_plan")
