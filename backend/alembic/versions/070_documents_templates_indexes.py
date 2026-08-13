"""índice faltando em document_folders.parent_folder_id (refatoração 070)

Revision ID: 070_documents_templates_indexes
Revises: 065_template_editor
Create Date: 2026-08-13

`DocumentFolderRepository.list_children`/`descendant_ids` (spec 063, regra 4 — cascata
de exclusão) filtram só por `parent_folder_id`, sem `scope_type`/`scope_id` no
predicado — o índice único composto da tabela (`tenant_id, scope_type, scope_id,
parent_folder_id, name`) não serve pra essa consulta porque `parent_folder_id` não é
coluna líder. Parcial (`WHERE parent_folder_id IS NOT NULL`): pasta raiz (a maioria,
na prática) não participa dessa busca.
"""

import sqlalchemy as sa

from alembic import op

revision: str = "070_documents_templates_indexes"
down_revision: str | None = "065_template_editor"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_index(
        "ix_document_folders_parent",
        "document_folders",
        ["parent_folder_id"],
        postgresql_where=sa.text("parent_folder_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_document_folders_parent", table_name="document_folders")
