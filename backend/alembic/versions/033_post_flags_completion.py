"""post flags + conclusão por responsável

Revision ID: 033_post_flags_completion
Revises: 032_posts
Create Date: 2026-08-02

Spec 033: flags no post (importante/urgente/futura/privada/agenda) e conclusão por
responsável em post_users (completed_at, points_earned, is_read, is_starred) +
completed_by (regra 9: ADMINISTRADOR concluindo por outro fica registrado — a spec
não modelou a coluna, mas exige o registro; ver Descobertas).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "033_post_flags_completion"
down_revision: str | None = "032_posts"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "posts",
        sa.Column("is_important", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "posts",
        sa.Column("is_urgent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "posts",
        sa.Column("is_future", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "posts",
        sa.Column("is_private", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "posts",
        sa.Column(
            "show_in_schedule", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )

    op.add_column(
        "post_users",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("post_users", sa.Column("points_earned", sa.Integer(), nullable=True))
    op.add_column(
        "post_users",
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "post_users",
        sa.Column("is_starred", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "post_users",
        sa.Column("completed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
    )

    op.execute(
        "CREATE INDEX ix_post_users_pending ON post_users (tenant_id, user_id) "
        "WHERE completed_at IS NULL"
    )
    op.execute(
        "CREATE INDEX ix_post_users_completed ON post_users "
        "(tenant_id, user_id, completed_at DESC) WHERE completed_at IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("post_users", "completed_by")
    op.drop_column("post_users", "is_starred")
    op.drop_column("post_users", "is_read")
    op.drop_column("post_users", "points_earned")
    op.drop_column("post_users", "completed_at")
    op.drop_column("posts", "show_in_schedule")
    op.drop_column("posts", "is_private")
    op.drop_column("posts", "is_future")
    op.drop_column("posts", "is_urgent")
    op.drop_column("posts", "is_important")
