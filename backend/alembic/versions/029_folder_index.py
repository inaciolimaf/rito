"""folder index

Revision ID: 029_folder_index
Revises: 027_lawsuits_list_indexes
Create Date: 2026-08-02

Índice trigram parcial para o autocomplete de pasta (spec 029 §4) — pasta é atributo,
não entidade, então nenhuma tabela nova. pg_trgm já existe (migration 002).
"""

from alembic import op

revision: str = "029_folder_index"
down_revision: str | None = "027_lawsuits_list_indexes"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_lawsuits_folder_trgm ON lawsuits USING gin (folder gin_trgm_ops) "
        "WHERE folder IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_lawsuits_folder_trgm")
