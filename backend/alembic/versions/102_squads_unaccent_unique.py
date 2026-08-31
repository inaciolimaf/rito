"""102: nome de time único ignorando acento e caixa (dívida nº 11)

Revision ID: 102_squads_unaccent
Revises: 099_migration_lock
Create Date: 2026-08-31

`squads` é a única das 5 taxonomias simples (013-019) cuja unicidade de nome ainda era
sensível a acento e caixa: uma `UniqueConstraint(tenant_id, name)` literal, enquanto
grupos de ação (014), tipos de ação (014), etapas (015) e origens (016) usam índice
funcional sobre `immutable_unaccent(lower(name))` desde a migration 014. Na prática o
escritório conseguia criar "Time A", "TIME A" e "Timé A" lado a lado — três times que
ninguém distingue numa lista.

`immutable_unaccent()` já existe (criada em 014_action_groups_types.py); esta migration
só a consome.

**O desempate acontece ANTES do índice.** Duplicatas que hoje são válidas passariam a
violar o índice novo, e a migration falharia no meio de um deploy. A regra é
determinística e conservadora: o mais antigo (`created_at`, `id` como desempate) mantém
o nome; os demais ganham sufixo " (2)", " (3)"… Renomear, nunca apagar — `squad_members`
tem FK para `squads`, e um time apagado levaria os membros junto.

`downgrade()` desfaz o índice e recria a constraint literal, mas **não** desfaz o
rename: para isso seria preciso saber quais sufixos foram nossos e quais o usuário já
tinha ("Time A (2)" é um nome perfeitamente válido). Um downgrade que adivinha é pior
que um que não tenta — ele apagaria um nome legítimo.
"""

from alembic import op

revision: str = "102_squads_unaccent"
down_revision: str | None = "099_migration_lock"
branch_labels: str | None = None
depends_on: str | None = None

_DESEMPATE = """
WITH ranked AS (
    SELECT id,
           row_number() OVER (
               PARTITION BY tenant_id, immutable_unaccent(lower(name))
               ORDER BY created_at, id
           ) AS rn
    FROM squads
)
UPDATE squads s
SET name = s.name || ' (' || r.rn || ')'
FROM ranked r
WHERE s.id = r.id AND r.rn > 1
"""


def upgrade() -> None:
    op.execute(_DESEMPATE)
    op.drop_constraint("uq_squads_tenant_name", "squads", type_="unique")
    op.execute(
        "CREATE UNIQUE INDEX uq_squads_tenant_name ON squads "
        "(tenant_id, immutable_unaccent(lower(name)))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX uq_squads_tenant_name")
    op.create_unique_constraint("uq_squads_tenant_name", "squads", ["tenant_id", "name"])
