"""closure_goals e a view materializada de pontuação mensal

Revision ID: 039_goals_scores
Revises: 038_workflows
Create Date: 2026-08-09

Spec 039 §4: meta mensal de fechamentos por grupo de ação (closure_goals, tabela de
domínio com RLS; a meta de pontos por usuário já existe — users.points_goal, spec 012)
e a view materializada user_monthly_scores, que agrega post_users por mês.

Dois detalhes de multi-tenancy que a view materializada impõe:

1. RLS não existe em materialized view — o isolamento na LEITURA é garantido pela view
   barreira `user_monthly_scores_visible`, que embute o filtro
   `tenant_id = current_setting('app.tenant_id')` na definição. A aplicação só consulta
   a barreira, então quem garante o tenant continua sendo o banco (CLAUDE.md §4), não
   um WHERE manual no código. A view é "security definer" (dono rito) com GRANT SELECT
   para rito_app — assim rito_app nem precisa enxergar a matview diretamente.

2. REFRESH só pode ser feito por quem é dono da matview e enxerga todas as linhas —
   rito_app está sob FORCE RLS e sem `app.tenant_id` setado veria zero linhas (o
   refresh esvaziaria a view). Por isso o refresh roda como superusuário (rito) no
   worker de manutenção (app/workers/scores.py), nunca pela conexão da aplicação.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "039_goals_scores"
down_revision: str | None = "038_workflows"
branch_labels: str | None = None
depends_on: str | None = None

_MATVIEW_SQL = """
SELECT pu.tenant_id,
       pu.user_id,
       date_trunc('month', pu.completed_at)::date AS month,
       COUNT(*) AS tasks_completed,
       COALESCE(SUM(pu.points_earned), 0) AS points,
       COUNT(*) FILTER (WHERE pu.completed_at::date <= p.deadline_date) AS on_time,
       COUNT(*) FILTER (WHERE pu.completed_at::date >  p.deadline_date) AS late
FROM post_users pu
JOIN posts p ON p.id = pu.post_id
WHERE pu.completed_at IS NOT NULL
GROUP BY 1, 2, 3
"""


def upgrade() -> None:
    op.create_table(
        "closure_goals",
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
        sa.Column("monthly_target", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("monthly_target >= 0", name="ck_closure_goals_target"),
        sa.UniqueConstraint("tenant_id", "action_group_id", name="uq_closure_goals_group"),
    )
    for statement in enable_rls_statements("closure_goals"):
        op.execute(statement)

    op.execute(f"CREATE MATERIALIZED VIEW user_monthly_scores AS {_MATVIEW_SQL}")
    # Índice único exigido pelo REFRESH ... CONCURRENTLY.
    op.execute("CREATE UNIQUE INDEX ux_ums ON user_monthly_scores (tenant_id, user_id, month)")
    # View barreira: embute o filtro de tenant para a aplicação nunca precisar dele.
    op.execute(
        "CREATE VIEW user_monthly_scores_visible AS "
        "SELECT tenant_id, user_id, month, tasks_completed, points, on_time, late "
        "FROM user_monthly_scores "
        "WHERE tenant_id = current_setting('app.tenant_id', true)::uuid"
    )
    op.execute("GRANT SELECT ON user_monthly_scores_visible TO rito_app")


def downgrade() -> None:
    op.execute("DROP VIEW user_monthly_scores_visible")
    op.execute("DROP MATERIALIZED VIEW user_monthly_scores")
    op.drop_table("closure_goals")
