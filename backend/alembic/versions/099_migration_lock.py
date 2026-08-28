"""099: trava de migration no boot.

Spec 099, regra 3. Quando N instâncias sobem ao mesmo tempo — que é o caso normal de um
deploy rolling —, todas correm `alembic upgrade head` ao mesmo tempo. O Alembic não tem
proteção contra isso: duas instâncias podem começar a mesma migration, e o resultado vai
de "erro esquisito no boot" a schema pela metade.

A trava é uma linha de uma tabela de uma linha só. Quem consegue gravar aplica; quem não
consegue espera a outra terminar e segue com o schema já novo. O `CHECK (id = 1)` é o que
garante que não existe uma segunda trava.

`locked_at` existe para o caso feio: instância que morreu com a trava na mão. Depois do
timeout a trava é considerada abandonada e pode ser tomada — sem isso, um `kill -9` no
meio de um deploy exigiria alguém entrar no banco à mão para o sistema voltar a subir.

Revision ID: 099_migration_lock
Revises: 098b_posts_trgm
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "099_migration_lock"
down_revision: str | None = "098b_posts_trgm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "migration_locks",
        sa.Column("id", sa.SmallInteger(), primary_key=True, server_default="1"),
        sa.Column("locked_by", sa.Text(), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_migration_locks_single_row"),
    )
    # Sem tenant_id e sem RLS de propósito: a trava é do CLUSTER, não de um escritório —
    # mesma natureza de `integration_health` (spec 049) e dos catálogos globais.
    op.execute("INSERT INTO migration_locks (id) VALUES (1)")


def downgrade() -> None:
    op.drop_table("migration_locks")
