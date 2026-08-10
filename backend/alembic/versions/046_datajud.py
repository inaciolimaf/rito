"""integration_alerts e cnj_movement_codes (spec 046 — DataJud: client)

Revision ID: 046_datajud
Revises: 045_publication_routing
Create Date: 2026-08-10

`integration_alerts.tenant_id` é nulo para alerta de SISTEMA (regra 3: a
`DATAJUD_API_KEY` é config global, não por tenant — um 401 afeta todo mundo
igual). A política de RLS por isso não é a `enable_rls_statements` padrão
(que exige match exato de tenant): linhas com `tenant_id IS NULL` ficam
visíveis para qualquer sessão, as demais isolam por tenant normalmente.

`cnj_movement_codes` é taxonomia global (mesmo padrão de `courts`, spec 021)
— sem tenant_id, sem RLS. Seed de 71 códigos reais (`movement_codes_seed.py`,
Descobertas da spec 046).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.domain.courts.movement_codes_seed import MOVEMENT_CODES

revision: str = "046_datajud"
down_revision: str | None = "045_publication_routing"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "integration_alerts",
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
            nullable=True,
        ),
        sa.Column("integration", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_alerts_open",
        "integration_alerts",
        ["integration", sa.text("created_at DESC")],
        postgresql_where=sa.text("resolved_at IS NULL"),
    )
    op.execute('ALTER TABLE "integration_alerts" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "integration_alerts" FORCE ROW LEVEL SECURITY')
    op.execute(
        'CREATE POLICY tenant_isolation ON "integration_alerts" '
        "USING (tenant_id IS NULL OR tenant_id = current_setting('app.tenant_id', true)::uuid) "
        "WITH CHECK (tenant_id IS NULL OR tenant_id = current_setting('app.tenant_id', true)::uuid)"
    )

    op.create_table(
        "cnj_movement_codes",
        sa.Column("code", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "parent_code", sa.Integer(), sa.ForeignKey("cnj_movement_codes.code"), nullable=True
        ),
    )
    movement_codes_table = sa.table(
        "cnj_movement_codes",
        sa.column("code", sa.Integer()),
        sa.column("name", sa.Text()),
    )
    op.bulk_insert(
        movement_codes_table,
        [{"code": code, "name": name} for code, name in MOVEMENT_CODES],
    )


def downgrade() -> None:
    op.drop_table("cnj_movement_codes")
    op.drop_table("integration_alerts")
