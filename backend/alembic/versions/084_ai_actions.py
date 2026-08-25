"""ações de escrita da IA e auditoria imutável

Revision ID: 084_ai_actions
Revises: 083_tool_calls
Create Date: 2026-08-26

Spec 084 §4: `ai_actions` (a proposta de escrita, esperando confirmação humana) e
`ai_audit_log` (o que a IA de fato gravou, com estado antes e depois).

`ai_audit_log` é **append-only garantido pelo banco** (regra 8), com duas travas:
1. `REVOKE UPDATE, DELETE` da role de aplicação — a rota não consegue nem tentar;
2. uma trigger `BEFORE UPDATE OR DELETE` que levanta exceção — pega também quem chega
   pelo superusuário (migration, script de manutenção, psql de madrugada).

Só a segunda sobrevive a um `GRANT` distraído, e é por isso que existem as duas: a
imutabilidade do histórico do que a IA fez é a garantia que sustenta a confiança em
tudo o mais desta fase.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "084_ai_actions"
down_revision: str | None = "083_tool_calls"
branch_labels: str | None = None
depends_on: str | None = None

ai_action_status = postgresql.ENUM(
    "pending",
    "approved",
    "rejected",
    "executed",
    "failed",
    "expired",
    name="ai_action_status",
)

_APPEND_ONLY_FUNCTION = """
CREATE OR REPLACE FUNCTION ai_audit_log_append_only()
RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'ai_audit_log é append-only (spec 084, regra 8): % não é permitido',
        TG_OP USING ERRCODE = 'insufficient_privilege';
END;
$$;
"""

_APPEND_ONLY_TRIGGER = """
CREATE TRIGGER trg_ai_audit_log_append_only
BEFORE UPDATE OR DELETE ON ai_audit_log
FOR EACH ROW EXECUTE FUNCTION ai_audit_log_append_only();
"""


def upgrade() -> None:
    op.create_table(
        "ai_actions",
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
            "thread_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_threads.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("arguments", postgresql.JSONB(), nullable=False),
        # O que será gravado, campo a campo — é o que a UI mostra antes de alguém clicar.
        sa.Column("preview", postgresql.JSONB(), nullable=False),
        sa.Column("before_state", postgresql.JSONB(), nullable=True),
        sa.Column(
            "status", ai_action_status, nullable=False, server_default=sa.text("'pending'")
        ),
        sa.Column("affected_type", sa.Text(), nullable=True),
        sa.Column("affected_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "decided_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        # Regra 4: proposta esquecida vira `expired` em 1 h.
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now() + interval '1 hour'"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    for statement in enable_rls_statements("ai_actions"):
        op.execute(statement)
    op.execute(
        "CREATE INDEX ix_ai_actions_pending ON ai_actions (tenant_id, user_id, created_at DESC) "
        "WHERE status = 'pending'"
    )

    op.create_table(
        "ai_audit_log",
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
            "action_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_actions.id"),
            nullable=False,
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("affected_type", sa.Text(), nullable=False),
        sa.Column("affected_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("before_state", postgresql.JSONB(), nullable=True),
        sa.Column("after_state", postgresql.JSONB(), nullable=True),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    for statement in enable_rls_statements("ai_audit_log"):
        op.execute(statement)
    op.execute(
        "CREATE INDEX ix_audit_affected ON ai_audit_log (tenant_id, affected_type, affected_id)"
    )

    # Regra 8, trava 1: a role da aplicação só insere e lê.
    op.execute("REVOKE UPDATE, DELETE ON ai_audit_log FROM rito_app")
    # Regra 8, trava 2: vale para qualquer role, inclusive superusuário.
    op.execute(_APPEND_ONLY_FUNCTION)
    op.execute(_APPEND_ONLY_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_ai_audit_log_append_only ON ai_audit_log")
    op.execute("DROP FUNCTION IF EXISTS ai_audit_log_append_only()")
    op.drop_table("ai_audit_log")
    op.drop_table("ai_actions")
    ai_action_status.drop(op.get_bind(), checkfirst=True)
