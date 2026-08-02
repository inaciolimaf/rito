"""posts e post_users (tarefas)

Revision ID: 032_posts
Revises: 031_task_types
Create Date: 2026-08-02
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "032_posts"
down_revision: str | None = "031_task_types"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "posts",
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
            "task_type_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("task_types.id"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("scheduled_date", sa.Date(), nullable=True),
        sa.Column("scheduled_time", sa.Time(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("deadline_date", sa.Date(), nullable=True),
        sa.Column("all_day", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("reward_snapshot", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "end_date IS NULL OR scheduled_date IS NULL OR end_date >= scheduled_date",
            name="ck_posts_end_after_scheduled",
        ),
        sa.CheckConstraint("end_time IS NULL OR end_date IS NOT NULL", name="ck_posts_end_time"),
    )
    op.create_index("ix_posts_lawsuit", "posts", ["lawsuit_id", sa.text("scheduled_date DESC")])
    op.execute(
        "CREATE INDEX ix_posts_deadline ON posts (tenant_id, deadline_date) "
        "WHERE deadline_date IS NOT NULL"
    )
    op.create_index("ix_posts_type", "posts", ["tenant_id", "task_type_id"])
    for statement in enable_rls_statements("posts"):
        op.execute(statement)

    op.create_table(
        "post_users",
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
            "post_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("posts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint("post_id", "user_id", name="uq_post_users_post_user"),
    )
    op.create_index("ix_post_users_user", "post_users", ["tenant_id", "user_id"])
    for statement in enable_rls_statements("post_users"):
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("post_users")
    op.drop_table("posts")
