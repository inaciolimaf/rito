"""publication_reads (spec 048 — Módulo Intimações)

Revision ID: 048_publication_reads
Revises: 047_datajud_sync
Create Date: 2026-08-11

Spec 048, §4: leitura é POR USUÁRIO (regra 5) — o que um advogado leu não marca
como lida para os outros. O §4 original desenha `PRIMARY KEY (publication_id,
user_id)`; aqui segue o padrão real do projeto (decisão da spec 013, repetida
em `post_users` da 032): PK surrogate `id` + UNIQUE(publication_id, user_id),
mesmo efeito de "no máximo uma marca por usuário" — ver Descobertas da 048.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls

revision: str = "048_publication_reads"
down_revision: str | None = "047_datajud_sync"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "publication_reads",
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
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "read_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("publication_id", "user_id", name="uq_publication_reads_pub_user"),
    )
    enable_rls("publication_reads")


def downgrade() -> None:
    op.drop_table("publication_reads")
