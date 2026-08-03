"""post_recurrences + posts.recurrence_id

Revision ID: 034_post_recurrences
Revises: 033_post_flags_completion
Create Date: 2026-08-03

Spec 034: séries de recorrência de tarefas — 8 periodicidades × 5 modos de repetição
no mês; cada ocorrência é um post independente ligado à série por posts.recurrence_id.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "034_post_recurrences"
down_revision: str | None = "033_post_flags_completion"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # create_table emite o CREATE TYPE dos enums sozinho (lição da 023/031: chamada
    # manual duplica) — por isso create_type=False na coluna do modelo, não aqui.
    recurrence_period = postgresql.ENUM(
        "DIARIA",
        "SEMANAL",
        "QUINZENAL",
        "MENSAL",
        "BIMESTRAL",
        "TRIMESTRAL",
        "SEMESTRAL",
        "ANUAL",
        name="recurrence_period",
    )
    recurrence_week = postgresql.ENUM(
        "DIA_EXATO", "PRIMEIRA", "SEGUNDA", "TERCEIRA", "ULTIMA", name="recurrence_week"
    )

    op.create_table(
        "post_recurrences",
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
            "template_post_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("posts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period", recurrence_period, nullable=False),
        sa.Column(
            "repeat_on", recurrence_week, nullable=False, server_default=sa.text("'DIA_EXATO'")
        ),
        sa.Column("until_date", sa.Date(), nullable=True),
        sa.Column("max_occurrences", sa.Integer(), nullable=True),
        sa.Column("occurrences_created", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_generated_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        # Regra 6: ao menos um limite precisa ser positivo quando informado.
        sa.CheckConstraint(
            "max_occurrences IS NULL OR max_occurrences > 0",
            name="ck_post_recurrences_max_occurrences",
        ),
        # Uma série por post template (o template É a primeira ocorrência).
        sa.UniqueConstraint("template_post_id", name="uq_post_recurrences_template"),
    )
    for statement in enable_rls_statements("post_recurrences"):
        op.execute(statement)

    # SET NULL: excluir uma ocorrência (regra 10) nunca interrompe a série — e se o
    # template cair pelo CASCADE, as ocorrências geradas sobrevivem sem o vínculo.
    op.add_column(
        "posts",
        sa.Column(
            "recurrence_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("post_recurrences.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.execute(
        "CREATE INDEX ix_posts_recurrence ON posts (recurrence_id) WHERE recurrence_id IS NOT NULL"
    )
    # Varredura do worker (regra 2): séries ativas cuja última data gerada já passou.
    op.execute(
        "CREATE INDEX ix_post_recurrences_sweep ON post_recurrences "
        "(tenant_id, last_generated_date) WHERE is_active"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_posts_recurrence")
    op.drop_column("posts", "recurrence_id")
    op.drop_table("post_recurrences")
    sa.Enum(name="recurrence_period").drop(op.get_bind())
    sa.Enum(name="recurrence_week").drop(op.get_bind())
