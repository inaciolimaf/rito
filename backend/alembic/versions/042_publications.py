"""publications, publication_recipients e publication_lawyers (DJEN)

Revision ID: 042_publications
Revises: 041_external_requests
Create Date: 2026-08-10

Spec 042, §4: comunicações capturadas do DJEN. `hash` é a chave de deduplicação
(UNIQUE por tenant, regra 2) e `availability_date` é a base legal da contagem de
prazo (regra 3). `lawsuit_id` fica nulo até o roteamento da spec 045.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls

revision: str = "042_publications"
down_revision: str | None = "041_external_requests"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "publications",
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
        sa.Column("external_id", sa.BigInteger(), nullable=False),
        sa.Column("hash", sa.Text(), nullable=False),
        sa.Column("availability_date", sa.Date(), nullable=False),
        sa.Column("court_code", sa.Text(), nullable=False),
        sa.Column("communication_type", sa.Text(), nullable=True),
        sa.Column("document_type", sa.Text(), nullable=True),
        sa.Column("organ_name", sa.Text(), nullable=True),
        sa.Column("organ_id", sa.Integer(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("process_number", sa.Text(), nullable=True),
        sa.Column("medium", sa.Text(), nullable=True),
        sa.Column("medium_full", sa.Text(), nullable=True),
        sa.Column("class_name", sa.Text(), nullable=True),
        sa.Column("class_code", sa.Integer(), nullable=True),
        sa.Column("communication_number", sa.Integer(), nullable=True),
        sa.Column("link", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("cancelled_at", sa.Date(), nullable=True),
        sa.Column(
            "lawsuit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lawsuits.id"),
            nullable=True,
        ),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "hash", name="uq_publications_tenant_hash"),
    )
    op.create_index(
        "ix_pub_availability",
        "publications",
        ["tenant_id", sa.text("availability_date DESC")],
    )
    op.create_index(
        "ix_pub_process",
        "publications",
        ["tenant_id", "process_number"],
        postgresql_where=sa.text("process_number IS NOT NULL"),
    )
    op.create_index(
        "ix_pub_lawsuit",
        "publications",
        ["lawsuit_id"],
        postgresql_where=sa.text("lawsuit_id IS NOT NULL"),
    )
    op.create_index(
        "ix_pub_unlinked",
        "publications",
        ["tenant_id", sa.text("availability_date DESC")],
        postgresql_where=sa.text("lawsuit_id IS NULL"),
    )

    op.create_table(
        "publication_recipients",
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
            "publication_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("pole", sa.Text(), nullable=True),
    )

    op.create_table(
        "publication_lawyers",
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
            "publication_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("publications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_lawyer_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("oab_number", sa.Text(), nullable=True),
        sa.Column("oab_state", sa.String(2), nullable=True),
    )
    op.create_index(
        "ix_pub_lawyers_ext",
        "publication_lawyers",
        ["tenant_id", "external_lawyer_id"],
    )

    for table in ("publications", "publication_recipients", "publication_lawyers"):
        enable_rls(table)


def downgrade() -> None:
    op.drop_table("publication_lawyers")
    op.drop_table("publication_recipients")
    op.drop_table("publications")
