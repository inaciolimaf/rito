"""locations

Revision ID: 018_locations
Revises: 017_customers
Create Date: 2026-08-01

"""

import csv
from pathlib import Path

import sqlalchemy as sa

from alembic import op

revision: str = "018_locations"
down_revision: str | None = "017_customers"
branch_labels: str | None = None
depends_on: str | None = None

# Dados reais do IBGE (https://servicodados.ibge.gov.br/api/v1/localidades) — 27 estados e
# 5.571 municípios, baixados uma vez e versionados como CSV. Grande demais para listar como
# literais Python (diferente dos seeds pequenos de 011/012/014/015/016/017); a migration só
# lê e faz bulk insert.
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _read_csv(name: str) -> list[dict[str, str]]:
    with (_DATA_DIR / name).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def upgrade() -> None:
    op.create_table(
        "states",
        sa.Column("code", sa.CHAR(2), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("ibge_code", sa.SmallInteger(), nullable=False, unique=True),
    )
    states_table = sa.table(
        "states",
        sa.column("code", sa.CHAR(2)),
        sa.column("name", sa.Text()),
        sa.column("ibge_code", sa.SmallInteger()),
    )
    op.bulk_insert(
        states_table,
        [
            {"code": row["code"], "name": row["name"], "ibge_code": int(row["ibge_code"])}
            for row in _read_csv("018_states.csv")
        ],
    )

    op.create_table(
        "cities",
        sa.Column("ibge_code", sa.Integer(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("state_code", sa.CHAR(2), sa.ForeignKey("states.code"), nullable=False),
    )
    op.create_index("ix_cities_state", "cities", ["state_code"])
    op.execute("CREATE INDEX ix_cities_name_trgm ON cities USING gin (name gin_trgm_ops)")

    cities_table = sa.table(
        "cities",
        sa.column("ibge_code", sa.Integer()),
        sa.column("name", sa.Text()),
        sa.column("state_code", sa.CHAR(2)),
    )
    op.bulk_insert(
        cities_table,
        [
            {
                "ibge_code": int(row["ibge_code"]),
                "name": row["name"],
                "state_code": row["state_code"],
            }
            for row in _read_csv("018_cities.csv")
        ],
    )


def downgrade() -> None:
    op.drop_table("cities")
    op.drop_table("states")
