"""098b: índice trigrama na busca de tarefas.

Spec 098, regras 2 e 4. O perfilamento noturno mostrou a busca global em 1,3 s contra
uma meta de 200 ms, e a faceta mais cara era a de tarefas.

A busca de tarefa é por `comments` e `location` com `ILIKE '%termo%'` — a spec 096
decidiu, corretamente, não dar `tsvector` próprio à tarefa (ela não tem texto seu; o
título vem do tipo). O que faltou foi o índice que torna esse `ILIKE` indexável:
curinga à ESQUERDA anula qualquer índice B-tree, e a única estrutura que o serve é o GIN
trigrama — que é exatamente o que contatos (`ix_customers_name_trgm`) e processos
(`ix_lawsuits_folder_trgm`) já tinham desde a 096.

Revision ID: 098b_posts_trgm
Revises: 098_fk_indexes
"""

from collections.abc import Sequence

from alembic import op

revision: str = "098b_posts_trgm"
down_revision: str | None = "098_fk_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `WHERE ... IS NOT NULL`: a maioria das tarefas não tem local preenchido, e índice
    # parcial não gasta espaço com o que nunca vai casar.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_posts_comments_trgm ON posts "
        "USING gin (comments gin_trgm_ops) WHERE comments IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_posts_location_trgm ON posts "
        "USING gin (location gin_trgm_ops) WHERE location IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_posts_comments_trgm")
    op.execute("DROP INDEX IF EXISTS ix_posts_location_trgm")
