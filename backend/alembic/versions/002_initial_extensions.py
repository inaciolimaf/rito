"""initial extensions

Revision ID: 002_initial_extensions
Revises:
Create Date: 2026-08-01

"""

from alembic import op

revision: str = "002_initial_extensions"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "unaccent"')


def downgrade() -> None:
    op.execute('DROP EXTENSION IF EXISTS "unaccent"')
    op.execute('DROP EXTENSION IF EXISTS "pg_trgm"')
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
