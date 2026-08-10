"""roteamento de publicação → tarefa (intimação → tarefa)

Revision ID: 045_publication_routing
Revises: 044_sync_control
Create Date: 2026-08-10

Spec 045, §4: casamento publicação↔processo e roteamento do responsável. O
resultado do algoritmo (§5) fica gravado em `matched_by`/`routed_to`/
`routed_by` para auditoria (regra 12); `post_id` é o vínculo com a tarefa
criada (regra 1: no máximo uma por publicação). `default_publications_user_id`
em `accounts` é a rota 3 (responsável geral) — nulo até o Gestor configurar.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "045_publication_routing"
down_revision: str | None = "044_sync_control"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "publications",
        sa.Column(
            "post_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("posts.id"), nullable=True
        ),
    )
    op.add_column("publications", sa.Column("matched_by", sa.Text(), nullable=True))
    op.add_column(
        "publications",
        sa.Column(
            "routed_to", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
    )
    op.add_column("publications", sa.Column("routed_by", sa.Text(), nullable=True))
    op.add_column(
        "publications", sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "ix_pub_unprocessed",
        "publications",
        ["tenant_id", "created_at"],
        postgresql_where=sa.text("processed_at IS NULL"),
    )

    op.add_column(
        "accounts",
        sa.Column(
            "default_publications_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("accounts", "default_publications_user_id")
    op.drop_index("ix_pub_unprocessed", table_name="publications")
    op.drop_column("publications", "processed_at")
    op.drop_column("publications", "routed_by")
    op.drop_column("publications", "routed_to")
    op.drop_column("publications", "matched_by")
    op.drop_column("publications", "post_id")
