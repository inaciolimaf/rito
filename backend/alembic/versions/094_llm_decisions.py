"""automação com decisão por LLM

Revision ID: 094_llm_decisions
Revises: 093_webhooks
Create Date: 2026-08-28

Spec 094: o nó que escolhe o ramo olhando o contexto, em vez de comparar um campo.

`automation_decisions` guarda o RACIOCÍNIO, e é a razão de a tabela existir: uma
automação que decide sem explicar não é auditável, e a pergunta que chega seis semanas
depois é sempre "por que ele mandou isso para o ramo urgente?". Guardar só o ramo
escolhido responderia "porque sim".

`branches` mora na própria ação de decisão (`{"ramo": [posições]}`) em vez de numa tabela
nova: o ramo não é uma entidade da vida do escritório, é a forma da automação — e uma
tabela a mais para representar forma custaria dois JOINs em toda leitura do editor.

O orçamento por automação é separado do teto global da 090 de propósito: aquele protege a
conta do escritório, este protege contra UMA automação mal escrita — a que roda em toda
intimação e consome sozinha o mês inteiro.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "094_llm_decisions"
down_revision: str | None = "093_webhooks"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "automation_actions",
        sa.Column("branches", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "automations",
        sa.Column("monthly_ai_budget_usd", sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        "automations",
        # 6 casas, e não 2: uma decisão custa centésimos de centavo, e um contador com
        # duas casas arredondaria toda chamada para zero — o teto nunca seria atingido.
        sa.Column(
            "current_month_spend_usd",
            sa.Numeric(12, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    # Sem a competência do contador, "gasto do mês" viraria "gasto desde sempre" na
    # virada — e a automação ficaria travada para o resto da vida depois do primeiro mês
    # caro.
    op.add_column("automations", sa.Column("spend_month", sa.Date(), nullable=True))
    # O ramo escolhido em cada decisão fica no estado da EXECUÇÃO: uma execução que
    # espera três dias no meio de um ramo precisa lembrar qual ramo era quando voltar.
    op.add_column(
        "automation_runs",
        sa.Column(
            "scratch",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    op.create_table(
        "automation_decisions",
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
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("automation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "action_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("automation_actions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("context_summary", sa.Text(), nullable=True),
        sa.Column("chosen_branch", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=True),
        # Regra 4: obrigatório. Automação que decide sem explicar não é auditável.
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column("fell_back", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        # Por que caiu no padrão: resposta fora da lista, confiança baixa, falha do
        # modelo ou orçamento estourado. Sem isso, `fell_back` diz que algo deu errado e
        # não diz o quê.
        sa.Column("fallback_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    for statement in enable_rls_statements("automation_decisions"):
        op.execute(statement)
    op.execute("CREATE INDEX ix_decisions_run ON automation_decisions (run_id, created_at)")


def downgrade() -> None:
    op.drop_table("automation_decisions")
    op.drop_column("automation_runs", "scratch")
    op.drop_column("automations", "spend_month")
    op.drop_column("automations", "current_month_spend_usd")
    op.drop_column("automations", "monthly_ai_budget_usd")
    op.drop_column("automation_actions", "branches")
