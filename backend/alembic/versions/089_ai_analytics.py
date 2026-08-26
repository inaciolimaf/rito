"""IA analítica — text-to-SQL guardrailed e insights

Revision ID: 089_ai_analytics
Revises: 088_editor_ai
Create Date: 2026-08-26

Spec 089 §4: `ai_sql_queries` (toda pergunta, com o SQL gerado e o veredito do
guardrail — inclusive as rejeitadas, regra 8 do §5), `ai_insights` (os avisos do job
diário) e a view `ai_allowed_metrics`, que é o catálogo analítico que o text-to-SQL
pode consultar.

`ai_allowed_metrics` é criada com **`security_invoker = true`**. Sem isso a view rodaria
com o RLS do DONO (o superusuário da migration) e devolveria o banco inteiro para
qualquer tenant — exatamente o vazamento que a spec 080 mapeou. Com o invoker, a
política de `lawsuits` continua valendo para quem consulta.

A view não expõe uma linha por processo: só agregados por mês, fase e grupo de ação.
Text-to-SQL sobre dado pessoal é uma porta que não precisa existir.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "089_ai_analytics"
down_revision: str | None = "088_editor_ai"
branch_labels: str | None = None
depends_on: str | None = None

_ALLOWED_METRICS = """
CREATE VIEW ai_allowed_metrics WITH (security_invoker = true) AS
SELECT l.tenant_id,
       (date_trunc('month', l.created_at))::date AS month,
       ag.name AS action_group,
       lt.name AS lawsuit_type,
       s.name  AS stage,
       st.name AS step,
       count(*)                                                   AS lawsuits,
       count(*) FILTER (WHERE l.closure_date IS NOT NULL)         AS closed,
       count(*) FILTER (WHERE l.archived_date IS NOT NULL)        AS archived,
       count(*) FILTER (WHERE l.is_archived)                      AS in_archive,
       count(*) FILTER (WHERE l.is_stagnant)                      AS stagnant,
       count(*) FILTER (WHERE l.outcome = 'GANHO')                AS won,
       count(*) FILTER (WHERE l.outcome = 'PERDIDO')              AS lost,
       count(*) FILTER (WHERE l.outcome = 'ACORDO')               AS settled,
       sum(l.case_value)                                          AS total_case_value,
       sum(l.fees_value) FILTER (WHERE l.closure_date IS NOT NULL) AS closed_fees
FROM lawsuits l
JOIN lawsuit_types lt ON lt.id = l.lawsuit_type_id
JOIN action_groups ag ON ag.id = lt.action_group_id
JOIN stages s ON s.id = l.stage_id
JOIN steps st ON st.id = s.step_id
GROUP BY 1, 2, 3, 4, 5, 6
"""


def upgrade() -> None:
    op.create_table(
        "ai_sql_queries",
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
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("generated_sql", sa.Text(), nullable=False),
        # Regra 8 do §5: a tentativa rejeitada é a que mais interessa auditar.
        sa.Column("was_allowed", sa.Boolean(), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    for statement in enable_rls_statements("ai_sql_queries"):
        op.execute(statement)

    op.create_table(
        "ai_insights",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        # 'deadline_risk' | 'stagnation' | 'overdue' | 'portfolio'
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        # Regra 12: todo insight aponta o registro que o originou.
        sa.Column("subject_type", sa.Text(), nullable=True),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("suggested_action", postgresql.JSONB(), nullable=True),
        sa.Column(
            "dismissed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    for statement in enable_rls_statements("ai_insights"):
        op.execute(statement)
    op.execute(
        "CREATE INDEX ix_insights_open ON ai_insights (tenant_id, severity, created_at DESC) "
        "WHERE dismissed_at IS NULL"
    )
    # Regra 10: um insight dispensado não volta nos próximos 30 dias — a busca por
    # "já dispensei isto?" é por (kind, subject_id).
    op.execute(
        "CREATE INDEX ix_insights_subject ON ai_insights (tenant_id, kind, subject_id, "
        "created_at DESC)"
    )

    op.execute(_ALLOWED_METRICS)
    op.execute("GRANT SELECT ON ai_allowed_metrics TO rito_app")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS ai_allowed_metrics")
    op.drop_table("ai_insights")
    op.drop_table("ai_sql_queries")
