"""templates.header_content/footer_content/watermark_text (spec 065 — Modelos: editor)

Revision ID: 065_template_editor
Revises: 064_templates
Create Date: 2026-08-13

Cabeçalho, rodapé e marca d'água ficam fora de `content` (regra 1): são texto do
documento, não do corpo editável do TipTap — por isso colunas próprias, não um objeto
dentro do HTML de `content`.
"""

import sqlalchemy as sa

from alembic import op

revision: str = "065_template_editor"
down_revision: str | None = "064_templates"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "templates",
        sa.Column("header_content", sa.Text(), nullable=False, server_default=sa.text("''")),
    )
    op.add_column(
        "templates",
        sa.Column("footer_content", sa.Text(), nullable=False, server_default=sa.text("''")),
    )
    op.add_column("templates", sa.Column("watermark_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("templates", "watermark_text")
    op.drop_column("templates", "footer_content")
    op.drop_column("templates", "header_content")
