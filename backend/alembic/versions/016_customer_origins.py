"""customer origins

Revision ID: 016_customer_origins
Revises: 015_steps_stages
Create Date: 2026-08-01

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "016_customer_origins"
down_revision: str | None = "015_steps_stages"
branch_labels: str | None = None
depends_on: str | None = None

# docs/ADVBOX-ESPECIFICACAO-COMPLETA.md §3.5 — 8 origens padrão.
_ORIGINS = [
    "ANÚNCIO",
    "ESCRITÓRIO",
    "FACEBOOK",
    "GOOGLE",
    "INDICAÇÃO",
    "INSTAGRAM",
    "PARTE CONTRÁRIA",
    "SITE DO ESCRITÓRIO",
]


def upgrade() -> None:
    op.create_table(
        "customer_origins",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    # Substitui o UNIQUE(tenant_id, name) simples da seção 4 da spec — regra 1 pede
    # comparação sem acento e sem diferenciar maiúsculas/minúsculas. immutable_unaccent()
    # já existe desde a migration 014 (mesma função, reaproveitada).
    op.execute(
        "CREATE UNIQUE INDEX uq_customer_origins_tenant_name ON customer_origins "
        "(tenant_id, immutable_unaccent(lower(name)))"
    )
    for statement in enable_rls_statements("customer_origins"):
        op.execute(statement)

    # Seed idempotente (só atinge tenants que já existem no momento da migration — mesma
    # limitação de 011/012/014/015, sem spec de provisionamento de tenant ainda).
    origin_values = ", ".join(f"('{name}')" for name in _ORIGINS)
    op.execute(f"""
        INSERT INTO customer_origins (tenant_id, name)
        SELECT t.id, o.name
        FROM tenants t
        CROSS JOIN (VALUES {origin_values}) AS o(name)
        ON CONFLICT (tenant_id, immutable_unaccent(lower(name))) DO NOTHING
        """)


def downgrade() -> None:
    op.drop_table("customer_origins")
