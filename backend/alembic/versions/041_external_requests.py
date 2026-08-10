"""external_requests — auditoria de chamadas HTTP externas

Revision ID: 041_external_requests
Revises: 039_goals_scores
Create Date: 2026-08-10

Spec 041, §4: toda falha de chamada externa (e uma amostra dos sucessos) é gravada
aqui — é a base do painel de observabilidade da sincronização (spec 049).

`tenant_id` é NULO em chamada de sistema (worker Celery sem tenant corrente), então
a tabela não segue o padrão NOT NULL das tabelas de domínio e a política RLS libera
a linha quando o tenant é NULL ou bate com o contexto. O NULLIF protege o cast: numa
conexão de pool já usada, o GUC "resetado" volta como string vazia e ''::uuid
levantaria erro em vez de simplesmente não casar (mesmo problema anotado em
tests/integration/test_rls.py).

Retenção de 30 dias: app/workers/external_requests.py (beat diário).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "041_external_requests"
down_revision: str | None = "039_goals_scores"
branch_labels: str | None = None
depends_on: str | None = None

_TENANT_PREDICATE = (
    "(tenant_id IS NULL OR " "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
)


def upgrade() -> None:
    op.create_table(
        "external_requests",
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
        sa.Column("host", sa.Text(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("status_code", sa.SmallInteger(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("attempt", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_ext_req_host",
        "external_requests",
        ["host", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_ext_req_error",
        "external_requests",
        ["host", sa.text("created_at DESC")],
        postgresql_where=sa.text("error IS NOT NULL"),
    )
    op.create_index("ix_external_requests_tenant", "external_requests", ["tenant_id"])

    op.execute("ALTER TABLE external_requests ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE external_requests FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON external_requests "
        f"USING {_TENANT_PREDICATE} WITH CHECK {_TENANT_PREDICATE}"
    )


def downgrade() -> None:
    op.drop_table("external_requests")
