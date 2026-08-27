"""busca global

Revision ID: 096_search
Revises: 095_api_tokens
Create Date: 2026-08-28

Spec 096. Duas colunas geradas e uma tabela de histórico.

As colunas são `GENERATED ALWAYS AS ... STORED` de propósito: com trigger, o índice fica
correto enquanto alguém lembrar de manter o trigger; com coluna gerada, o Postgres é quem
lembra. O custo é que a expressão vira parte do schema — mudar o que entra na busca exige
migração, e isso é bom: mudar o que entra na busca É uma mudança de contrato.

`unaccent` não é IMMUTABLE por padrão (depende do dicionário instalado), e coluna gerada
exige imutabilidade. A saída é uma função própria marcada IMMUTABLE que fixa o dicionário
— a mesma solução que a 014 já usava para o índice único sem acento.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "096_search"
down_revision: str | None = "095_api_tokens"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # IMMUTABLE mentiroso? Não: o dicionário é fixado no corpo, então para um mesmo texto
    # a saída é sempre a mesma. É a receita da documentação do Postgres para o caso.
    op.execute("""
        CREATE OR REPLACE FUNCTION rito_unaccent(text)
        RETURNS text
        LANGUAGE sql
        IMMUTABLE
        PARALLEL SAFE
        STRICT
        AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$;
        """)
    op.execute("""
        ALTER TABLE customers ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            to_tsvector(
                'portuguese',
                rito_unaccent(
                    coalesce(name, '') || ' ' ||
                    coalesce(identification, '') || ' ' ||
                    coalesce(email, '')
                )
            )
        ) STORED
        """)
    op.execute("CREATE INDEX ix_customers_fts ON customers USING gin (search_vector)")
    op.execute("""
        ALTER TABLE lawsuits ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            to_tsvector(
                'portuguese',
                rito_unaccent(
                    coalesce(process_number, '') || ' ' ||
                    coalesce(protocol_number, '') || ' ' ||
                    coalesce(folder, '') || ' ' ||
                    coalesce(notes, '')
                )
            )
        ) STORED
        """)
    op.execute("CREATE INDEX ix_lawsuits_fts ON lawsuits USING gin (search_vector)")

    op.create_table(
        "search_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("clicked_type", sa.Text(), nullable=True),
        sa.Column("clicked_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    for statement in enable_rls_statements("search_history"):
        op.execute(statement)
    op.execute("CREATE INDEX ix_search_history ON search_history (user_id, created_at DESC)")


def downgrade() -> None:
    op.drop_table("search_history")
    op.execute("DROP INDEX IF EXISTS ix_lawsuits_fts")
    op.execute("ALTER TABLE lawsuits DROP COLUMN IF EXISTS search_vector")
    op.execute("DROP INDEX IF EXISTS ix_customers_fts")
    op.execute("ALTER TABLE customers DROP COLUMN IF EXISTS search_vector")
    op.execute("DROP FUNCTION IF EXISTS rito_unaccent(text)")
