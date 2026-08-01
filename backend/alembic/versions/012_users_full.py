"""users full

Revision ID: 012_users_full
Revises: 011_accounts
Create Date: 2026-08-01

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "012_users_full"
down_revision: str | None = "011_accounts"
branch_labels: str | None = None
depends_on: str | None = None

# docs/ADVBOX-ESPECIFICACAO-COMPLETA.md linha 365 — 67 nomes únicos, apesar do rótulo
# "66 Cargos" na própria fonte (spec 012, Descobertas): a lista real tem 1 duplicata
# exata ("Assistente Jurídico"), removida; o restante é o levantamento, não invenção.
_OCCUPATIONS = [
    "Advogado Gestor",
    "Advogado Técnico",
    "Advogado Comercial",
    "Advogado Marketing",
    "Controller Jurídico",
    "Financeiro",
    "Parceiro",
    "Analista de Suporte",
    "Gerente de Tecnologia",
    "Departamento",
    "Desenvolvedor",
    "Diretor",
    "Assistente Administrativo",
    "Analista de Dados",
    "Estagiário",
    "Financeiro e RH",
    "Programador ou TI",
    "Administrador",
    "Médico",
    "Motorista",
    "Assistente Jurídico",
    "Analista de CS",
    "Psicólogo",
    "Recepcionista",
    "Profissional de RH",
    "SDR - Pré-Vendas",
    "Secretário",
    "Advogado Sócio Sem Atuação",
    "Suporte",
    "Supervisor",
    "Técnico",
    "Terceirizado",
    "Tesoureira",
    "Trainee",
    "Treinador",
    "Zelador",
    "Outra Função Não Listada",
    "Assistente Financeiro",
    "Administrativo e Financeiro",
    "Usuário Externo",
    "Secretaria",
    "Agente ou Captador",
    "Auxiliar Jurídico",
    "Estagiário de Direito",
    "Estagiário de Marketing",
    "Estagiário de Administrativo",
    "Estagiário de Financeiro",
    "Estagiário Outras Áreas",
    "Analista Jurídico",
    "Assessor Jurídico",
    "Atendente",
    "Assistente de Marketing",
    "Administrativo",
    "Gestor Jurídico",
    "Coordenador Jurídico",
    "Coordenador Comercial",
    "Coordenador de Marketing",
    "Coordenador de Atendimento",
    "Gerente Jurídico",
    "Gerente de Marketing",
    "Gerente de Atendimento",
    "Gerente Comercial",
    "Fechador de Contratos",
    "Consultor Jurídico",
    "Contador",
    "Advogado Parceiro",
    "Correspondente",
]

_occupations_table = sa.table(
    "occupations", sa.column("id", sa.SmallInteger()), sa.column("name", sa.Text())
)


def upgrade() -> None:
    op.create_table(
        "occupations",
        sa.Column("id", sa.SmallInteger(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
    )
    op.bulk_insert(
        _occupations_table,
        [{"id": index, "name": name} for index, name in enumerate(_OCCUPATIONS, start=1)],
    )

    op.add_column(
        "users", sa.Column("occupation_id", sa.SmallInteger(), sa.ForeignKey("occupations.id"))
    )
    op.add_column("users", sa.Column("identification", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("document", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("birthdate", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("number_ctps", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("number_oab", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("cellphone", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("phone", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("avatar_key", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("salary", sa.Numeric(12, 2), nullable=True))
    op.add_column("users", sa.Column("admission_date", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("resignation_date", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("work_start", sa.Time(), nullable=True))
    op.add_column("users", sa.Column("work_interval", sa.Interval(), nullable=True))
    op.add_column("users", sa.Column("work_end", sa.Time(), nullable=True))
    op.add_column("users", sa.Column("points_goal", sa.Integer(), nullable=True))
    op.add_column(
        "users",
        sa.Column("report_deadline", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "users",
        sa.Column("report_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "users",
        sa.Column("is_responsible", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_users_occupation_id", "users", ["occupation_id"])

    op.create_table(
        "user_invitations",
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
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM(
                "GESTOR", "ADMINISTRADOR", "COLABORADOR", name="user_role", create_type=False
            ),
            nullable=False,
        ),
        sa.Column(
            "financial_access",
            postgresql.ENUM(
                "NONE", "READ_ONLY", "FULL", name="financial_access", create_type=False
            ),
            nullable=False,
            server_default="NONE",
        ),
        sa.Column(
            "occupation_id", sa.SmallInteger(), sa.ForeignKey("occupations.id"), nullable=True
        ),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "invited_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
    )
    op.create_index("ix_user_invitations_invited_by", "user_invitations", ["invited_by"])
    for statement in enable_rls_statements("user_invitations"):
        op.execute(statement)

    op.add_column(
        "accounts",
        sa.Column(
            "track_access_logs", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )


def downgrade() -> None:
    op.drop_column("accounts", "track_access_logs")
    op.drop_table("user_invitations")
    op.drop_index("ix_users_occupation_id", table_name="users")
    for column in (
        "is_responsible",
        "report_deleted",
        "report_deadline",
        "points_goal",
        "work_end",
        "work_interval",
        "work_start",
        "resignation_date",
        "admission_date",
        "salary",
        "avatar_key",
        "phone",
        "cellphone",
        "number_oab",
        "number_ctps",
        "birthdate",
        "document",
        "identification",
        "occupation_id",
    ):
        op.drop_column("users", column)
    op.drop_table("occupations")
