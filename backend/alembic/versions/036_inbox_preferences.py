"""inbox_preferences (ordem das seções da caixa de entrada)

Revision ID: 036_inbox_preferences
Revises: 035_comments_attach_notifs
Create Date: 2026-08-03

Spec 036: ordem das 6 seções e seções colapsadas por usuário. PK surrogate `id` +
UNIQUE(user_id) — padrão Base de todo o projeto (mesma decisão da 013/032); o efeito
da PK (user_id) da spec é o mesmo: uma linha por usuário.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "036_inbox_preferences"
down_revision: str | None = "035_comments_attach_notifs"
branch_labels: str | None = None
depends_on: str | None = None

_DEFAULT_ORDER = "ARRAY['deadline','publications','unread','urgent','important','others']"


def upgrade() -> None:
    op.create_table(
        "inbox_preferences",
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
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "section_order",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text(_DEFAULT_ORDER),
        ),
        sa.Column(
            "collapsed_sections",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "page_size",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("100"),
        ),
        sa.UniqueConstraint("user_id", name="uq_inbox_preferences_user"),
    )
    for statement in enable_rls_statements("inbox_preferences"):
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("inbox_preferences")
