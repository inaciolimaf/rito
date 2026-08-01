"""action groups types

Revision ID: 014_action_groups_types
Revises: 013_squads
Create Date: 2026-08-01

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "014_action_groups_types"
down_revision: str | None = "013_squads"
branch_labels: str | None = None
depends_on: str | None = None

# Regra 1: nome único por tenant, "case-insensitive e sem acento" — unaccent() do Postgres
# é STABLE, não IMMUTABLE, então não pode entrar direto num índice (Postgres exige
# IMMUTABLE em expressão de índice). Este wrapper existe só para isso; reaproveitado por
# 015/016 (mesma regra de unicidade normalizada).
_CREATE_IMMUTABLE_UNACCENT = """
CREATE OR REPLACE FUNCTION immutable_unaccent(text)
RETURNS text AS $$
    SELECT public.unaccent('unaccent', $1)
$$ LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
"""

# docs/ADVBOX-ESPECIFICACAO-COMPLETA.md linha 330 (grupos) e 333 (tipos) — ambas listas
# "flat", sem a ADVBOX declarar qual tipo pertence a qual grupo ("exemplos da conta
# demo"). O pareamento abaixo é inferência a partir do nome (spec 014, Descobertas), não
# algo levantado explicitamente na fonte.
_GROUPS = [
    "ADMINISTRATIVO",
    "CÍVEL",
    "FINANCEIRO/RH",
    "PENAL",
    "PREVIDENCIÁRIO",
    "TRABALHISTA",
]

_TYPES_BY_GROUP = [
    ("ACUSAÇÃO DE ESTELIONATO", "PENAL"),
    ("ADMISSÃO DE FUNCIONÁRIO", "FINANCEIRO/RH"),
    ("APOSENTADORIA POR IDADE", "PREVIDENCIÁRIO"),
    ("CONCESSÃO DE FÉRIAS", "FINANCEIRO/RH"),
    ("CONCESSÃO DE FOLGA", "FINANCEIRO/RH"),
    ("DEMISSÃO DE FUNCIONÁRIO", "FINANCEIRO/RH"),
    ("JUSTIFICAÇÃO DE FALTA", "FINANCEIRO/RH"),
    ("NULIDADE DE LICITAÇÃO", "ADMINISTRATIVO"),
    ("RECLAMATÓRIA TRABALHISTA", "TRABALHISTA"),
    ("REINTEGRAÇÃO DE POSSE", "CÍVEL"),
]


def upgrade() -> None:
    op.execute(_CREATE_IMMUTABLE_UNACCENT)

    op.create_table(
        "action_groups",
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
        sa.Column(
            "publications_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_action_groups_publications_user_id", "action_groups", ["publications_user_id"]
    )
    # Substitui a UNIQUE(tenant_id, name) simples da seção 4 — regra 1 pede comparação
    # sem acento e sem diferenciar maiúsculas/minúsculas, não igualdade literal de bytes.
    op.execute(
        "CREATE UNIQUE INDEX uq_action_groups_tenant_name ON action_groups "
        "(tenant_id, immutable_unaccent(lower(name)))"
    )
    for statement in enable_rls_statements("action_groups"):
        op.execute(statement)

    op.create_table(
        "lawsuit_types",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column(
            "action_group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("action_groups.id"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_lawsuit_types_group", "lawsuit_types", ["action_group_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_lawsuit_types_tenant_name ON lawsuit_types "
        "(tenant_id, immutable_unaccent(lower(name)))"
    )
    for statement in enable_rls_statements("lawsuit_types"):
        op.execute(statement)

    # Seed idempotente (spec 014, seção 4/10) — só afeta tenants que já existem no
    # momento em que a migration roda; nenhuma spec de provisionamento de tenant existe
    # ainda (011/012, Descobertas), então tenants criados depois (inclusive em teste, via
    # `make_user`) não ganham grupos/tipos automaticamente — cada teste cria os próprios
    # via API, igual squads/users já fazem.
    group_values = ", ".join(f"('{name}')" for name in _GROUPS)
    op.execute(f"""
        INSERT INTO action_groups (tenant_id, name)
        SELECT t.id, g.name
        FROM tenants t
        CROSS JOIN (VALUES {group_values}) AS g(name)
        ON CONFLICT (tenant_id, immutable_unaccent(lower(name))) DO NOTHING
        """)

    type_values = ", ".join(
        f"('{type_name}', '{group_name}')" for type_name, group_name in _TYPES_BY_GROUP
    )
    op.execute(f"""
        INSERT INTO lawsuit_types (tenant_id, action_group_id, name)
        SELECT ag.tenant_id, ag.id, tt.type_name
        FROM action_groups ag
        JOIN (VALUES {type_values}) AS tt(type_name, group_name)
          ON ag.name = tt.group_name
        ON CONFLICT (tenant_id, immutable_unaccent(lower(name))) DO NOTHING
        """)


def downgrade() -> None:
    op.drop_table("lawsuit_types")
    op.drop_table("action_groups")
    op.execute("DROP FUNCTION IF EXISTS immutable_unaccent(text)")
