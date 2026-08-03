"""post_comments + attachments + notifications

Revision ID: 035_comments_attach_notifs
Revises: 034_post_recurrences
Create Date: 2026-08-03

Spec 035: thread de comentários com @menções (ids persistidos — regra 1), anexos
genéricos (attachments serve posts, comentários e, no futuro, contatos/financeiro)
e notificações in-app genéricas (o roteamento por canal é da 069). Revision id curto
de propósito: alembic_version.version_num é varchar(32).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "035_comments_attach_notifs"
down_revision: str | None = "034_post_recurrences"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "post_comments",
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
            "author_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        # Regra 1: menções persistem como ids — renomear o usuário não quebra o link.
        sa.Column(
            "mentioned_user_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        # Regra 4: exclusão é soft — a thread se preserva com "comentário removido".
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_comments_post", "post_comments", ["post_id", sa.text("created_at")])
    for statement in enable_rls_statements("post_comments"):
        op.execute(statement)

    op.create_table(
        "attachments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        # Genérico: 'post' e 'comment' agora; 'customer'/'transaction' chegam com as
        # specs deles — a validação vive no service, não em FK.
        sa.Column("attached_to_type", sa.Text(), nullable=False),
        sa.Column("attached_to_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "uploaded_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        # Regra 5: tamanho máximo 50 MB também no banco (defesa em profundidade).
        sa.CheckConstraint(
            "size_bytes >= 0 AND size_bytes <= 52428800", name="ck_attachments_size"
        ),
    )
    op.create_index(
        "ix_attachments_target",
        "attachments",
        ["tenant_id", "attached_to_type", "attached_to_id"],
    )
    for statement in enable_rls_statements("attachments"):
        op.execute(statement)

    op.create_table(
        "notifications",
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
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("link", sa.Text(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.execute(
        "CREATE INDEX ix_notifications_unread ON notifications "
        "(tenant_id, user_id, created_at DESC) WHERE read_at IS NULL"
    )
    for statement in enable_rls_statements("notifications"):
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("attachments")
    op.drop_table("post_comments")
