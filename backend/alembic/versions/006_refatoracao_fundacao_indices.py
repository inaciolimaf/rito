"""refatoracao fundacao indices

Revision ID: 006_refatoracao_fundacao_indices
Revises: 005_rbac
Create Date: 2026-08-01

"""

from alembic import op

revision: str = "006_refatoracao_fundacao_indices"
down_revision: str | None = "005_rbac"
branch_labels: str | None = None
depends_on: str | None = None

# Spec 010 (refatoração), checklist "Banco": toda FK precisa de índice e todo filtro
# frequente também. user_id (FK em refresh_tokens/password_reset_tokens) nunca tinha
# índice; family_id é filtrado a cada refresh e na detecção de reuso de token
# (AuthService.refresh) e também não tinha.
_INDEXES = [
    ("ix_refresh_tokens_user_id", "refresh_tokens", "user_id"),
    ("ix_refresh_tokens_family_id", "refresh_tokens", "family_id"),
    ("ix_password_reset_tokens_user_id", "password_reset_tokens", "user_id"),
]


def upgrade() -> None:
    for index_name, table_name, column_name in _INDEXES:
        op.create_index(index_name, table_name, [column_name])


def downgrade() -> None:
    for index_name, table_name, _ in _INDEXES:
        op.drop_index(index_name, table_name=table_name)
