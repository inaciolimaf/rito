"""customers

Revision ID: 017_customers
Revises: 016_customer_origins
Create Date: 2026-08-01

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "017_customers"
down_revision: str | None = "016_customer_origins"
branch_labels: str | None = None
depends_on: str | None = None

_person_type = postgresql.ENUM("PF", "PJ", name="person_type", create_type=False)

# docs/ADVBOX-ESPECIFICACAO-COMPLETA.md §2.1 — 6 estados civis.
_MARITAL_STATUSES = [
    "CASADO(A)",
    "DIVORCIADO(A)",
    "SEPARADO(A)",
    "SOLTEIRO(A)",
    "UNIÃO ESTÁVEL",
    "VIÚVO(A)",
]


def upgrade() -> None:
    _person_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "marital_statuses",
        sa.Column("id", sa.SmallInteger(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
    )
    marital_statuses_table = sa.table(
        "marital_statuses", sa.column("id", sa.SmallInteger()), sa.column("name", sa.Text())
    )
    op.bulk_insert(
        marital_statuses_table,
        [{"id": index, "name": name} for index, name in enumerate(_MARITAL_STATUSES, start=1)],
    )

    op.create_table(
        "customers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("type", _person_type, nullable=False, server_default="PF"),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("identification", sa.Text(), nullable=True),
        sa.Column("document", sa.Text(), nullable=True),
        sa.Column(
            "origin_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customer_origins.id"),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("birthdate", sa.Date(), nullable=True),
        sa.Column(
            "marital_status_id",
            sa.SmallInteger(),
            sa.ForeignKey("marital_statuses.id"),
            nullable=True,
        ),
        sa.Column("occupation", sa.Text(), nullable=True),
        sa.Column("gender", sa.Text(), nullable=True),
        sa.Column("nationality", sa.Text(), nullable=True),
        sa.Column("mother_name", sa.Text(), nullable=True),
        sa.Column("cellphone", sa.Text(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("email", postgresql.CITEXT(), nullable=True),
        sa.Column("country", sa.Text(), nullable=False, server_default="BRASIL"),
        sa.Column("postal_code", sa.Text(), nullable=True),
        sa.Column("state", sa.CHAR(2), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("street", sa.Text(), nullable=True),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("number_pis", sa.Text(), nullable=True),
        sa.Column("number_ctps", sa.Text(), nullable=True),
        sa.Column("number_cid", sa.Text(), nullable=True),
        sa.Column("photo_key", sa.Text(), nullable=True),
        sa.Column(
            "has_representative", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("rep_name", sa.Text(), nullable=True),
        sa.Column("rep_identification", sa.Text(), nullable=True),
        sa.Column("rep_document", sa.Text(), nullable=True),
        sa.Column("rep_birthdate", sa.Date(), nullable=True),
        sa.Column("rep_country", sa.Text(), nullable=True),
        sa.Column("rep_state", sa.CHAR(2), nullable=True),
        sa.Column("rep_city", sa.Text(), nullable=True),
        sa.Column("rep_street", sa.Text(), nullable=True),
        sa.Column("rep_region", sa.Text(), nullable=True),
        sa.Column("rep_postal_code", sa.Text(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "NOT has_representative OR rep_name IS NOT NULL", name="ck_customers_representative"
        ),
        # Regra 7: sexo só aceita F ou M (campo opcional, então NULL também é válido).
        sa.CheckConstraint("gender IS NULL OR gender IN ('F', 'M')", name="ck_customers_gender"),
    )
    op.create_index("ix_customers_origin", "customers", ["origin_id"])
    op.create_index("ix_customers_marital_status", "customers", ["marital_status_id"])
    # `identification` é opcional (regra 3) — índice parcial permite quantos NULL quiser,
    # só bloqueia duplicidade entre valores informados.
    op.execute(
        "CREATE UNIQUE INDEX uq_customers_tenant_identification ON customers "
        "(tenant_id, identification) WHERE identification IS NOT NULL"
    )
    # Regra 8: nome buscável por trecho, sem acento — mesma immutable_unaccent() da 014,
    # agora num índice GIN trigram (pg_trgm, já habilitada desde a 002) em vez de um índice
    # de igualdade único (aqui não há unicidade de nome, é busca por substring).
    op.execute(
        "CREATE INDEX ix_customers_name_trgm ON customers "
        "USING gin (immutable_unaccent(lower(name)) gin_trgm_ops)"
    )
    for statement in enable_rls_statements("customers"):
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("customers")
    op.drop_table("marital_statuses")
    _person_type.drop(op.get_bind(), checkfirst=True)
