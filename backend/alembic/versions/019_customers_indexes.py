"""customers indexes

Revision ID: 019_customers_indexes
Revises: 018_locations
Create Date: 2026-08-01

"""

from alembic import op

revision: str = "019_customers_indexes"
down_revision: str | None = "018_locations"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # `ix_customers_origin` (origin_id puro) e `ix_customers_name_trgm`
    # (immutable_unaccent(lower(name)) gin_trgm_ops) já existem desde a migration 017 —
    # a segunda já é estritamente melhor que a versão sem unaccent da seção 4 desta spec
    # (busca "sem acento", regra 1). `ix_customers_origin_active` abaixo é uma variante
    # nova (parcial, só linhas não arquivadas) para a agregação de Top Origens/stats, daí
    # o nome diferente — mesmo nome colidiria com o índice de 017.
    op.execute(
        "CREATE INDEX ix_customers_origin_active ON customers (tenant_id, origin_id) "
        "WHERE NOT is_archived"
    )
    op.execute(
        "CREATE INDEX ix_customers_birthdate ON customers "
        "(tenant_id, (EXTRACT(MONTH FROM birthdate)), (EXTRACT(DAY FROM birthdate)))"
    )
    op.create_index("ix_customers_created", "customers", ["tenant_id", "created_at"])
    op.execute(
        "CREATE INDEX ix_customers_occupation ON customers (tenant_id, occupation) "
        "WHERE occupation IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_customers_occupation", table_name="customers")
    op.drop_index("ix_customers_created", table_name="customers")
    op.drop_index("ix_customers_birthdate", table_name="customers")
    op.drop_index("ix_customers_origin_active", table_name="customers")
