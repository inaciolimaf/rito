"""dre_groups + financial_categories + cost_centers (spec 054 — Financeiro: plano
de contas)

Revision ID: 054_chart_of_accounts
Revises: 053_workflow_applications
Create Date: 2026-08-11

`dre_groups` é global e imutável (10 grupos fixos, como `steps`/`courts`) — sem
tenant_id, sem RLS. `financial_categories`/`cost_centers` são por tenant, com RLS.
Seed idempotente das 61 categorias e do centro `GERAL`: só atinge tenants que já
existem no momento da migration — mesma limitação já documentada em 011/012/014/015
(sem spec de provisionamento de tenant ainda; ver Descobertas da spec 054).

Fonte: docs/ADVBOX-ESPECIFICACAO-COMPLETA.md §3.9. As duas exceções semeadas
(PAGAMENTO DE FATURA e REEMBOLSO DE CUSTO POR CLIENTES, tipo RECEITA em grupos de
natureza DESPESA) são do dado real do ADVBOX, não um erro de digitação — regra 2.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "054_chart_of_accounts"
down_revision: str | None = "053_workflow_applications"
branch_labels: str | None = None
depends_on: str | None = None

# id, name, nature ('RECEITA'|'DESPESA')
_DRE_GROUPS: list[tuple[int, str, str]] = [
    (0, "Deduções da receita bruta", "DESPESA"),
    (1, "Receitas", "RECEITA"),
    (2, "Folha de pagamento", "DESPESA"),
    (3, "Encargos sociais", "DESPESA"),
    (4, "Tributos", "DESPESA"),
    (5, "Despesas fixas", "DESPESA"),
    (6, "Despesas variáveis", "DESPESA"),
    (7, "Despesas bancárias", "DESPESA"),
    (8, "Marketing e comercial", "DESPESA"),
    (9, "Distribuição de lucros e participação", "DESPESA"),
]

# name, type, dre_group_id — 14 RECEITA + 47 DESPESA = 61 (docs §3.9).
_CATEGORIES: list[tuple[str, str, int]] = [
    # RECEITA (12 no grupo 1, natural).
    ("HONORÁRIOS INICIAIS", "RECEITA", 1),
    ("HONORÁRIOS FINAIS", "RECEITA", 1),
    ("HONORÁRIOS DE SUCUMBÊNCIA", "RECEITA", 1),
    ("HONORÁRIOS CONSULTORIAS", "RECEITA", 1),
    ("HONORÁRIOS POR MENSALIDADE", "RECEITA", 1),
    ("RPVS", "RECEITA", 1),
    ("PRECATÓRIOS", "RECEITA", 1),
    ("ALVARÁS", "RECEITA", 1),
    ("MULTA E JUROS", "RECEITA", 1),
    ("APLICAÇÕES FINANCEIRAS", "RECEITA", 1),
    ("APORTE DE SÓCIO", "RECEITA", 1),
    ("INTEGRALIZAÇÃO DE SÓCIO", "RECEITA", 1),
    # RECEITA — 2 exceções reais do ADVBOX (regra 2): tipo RECEITA em grupo DESPESA.
    ("PAGAMENTO DE FATURA", "RECEITA", 5),
    ("REEMBOLSO DE CUSTO POR CLIENTES", "RECEITA", 6),
    # DESPESA — grupo 0.
    ("HONORÁRIOS DE PARCEIROS", "DESPESA", 0),
    ("HONORÁRIOS DE ADVOGADOS ASSOCIADOS", "DESPESA", 0),
    # DESPESA — grupo 2 (folha de pagamento).
    ("ADIANTAMENTOS", "DESPESA", 2),
    ("RESCISÃO DO CONTRATO DE TRABALHO", "DESPESA", 2),
    ("ABONO PRODUTIVIDADE", "DESPESA", 2),
    ("REMUNERAÇÃO DE FUNCIONÁRIOS", "DESPESA", 2),
    ("HORAS EXTRAS", "DESPESA", 2),
    ("FÉRIAS", "DESPESA", 2),
    ("SALÁRIOS", "DESPESA", 2),
    ("PRÓ-LABORE", "DESPESA", 2),
    ("VALE TRANSPORTE", "DESPESA", 2),
    ("VALE ALIMENTAÇÃO", "DESPESA", 2),
    # DESPESA — grupo 3 (encargos sociais).
    ("FGTS", "DESPESA", 3),
    # DESPESA — grupo 4 (tributos).
    ("SIMPLES NACIONAL", "DESPESA", 4),
    ("IPTU", "DESPESA", 4),
    ("IOF", "DESPESA", 4),
    ("INSS", "DESPESA", 4),
    ("OUTROS IMPOSTOS", "DESPESA", 4),
    # DESPESA — grupo 5 (despesas fixas).
    ("ÁGUA", "DESPESA", 5),
    ("CONTADOR", "DESPESA", 5),
    ("TELEFONIA", "DESPESA", 5),
    ("CONDOMÍNIO", "DESPESA", 5),
    ("ANUIDADE OAB", "DESPESA", 5),
    ("ENERGIA ELÉTRICA", "DESPESA", 5),
    ("ALUGUEL", "DESPESA", 5),
    ("INTERNET", "DESPESA", 5),
    # DESPESA — grupo 6 (despesas variáveis).
    ("MULTAS JUDICIAIS", "DESPESA", 6),
    ("DESPESAS DE CARTÓRIO", "DESPESA", 6),
    ("RESSARCIMENTO CUSTO AO FUNCIONÁRIO", "DESPESA", 6),
    ("MÓVEIS", "DESPESA", 6),
    ("CURSOS E TREINAMENTOS", "DESPESA", 6),
    ("MATERIAIS DE CONSTRUÇÃO", "DESPESA", 6),
    ("HOTEL", "DESPESA", 6),
    ("MATERIAIS DO ESCRITÓRIO", "DESPESA", 6),
    ("CORREIOS", "DESPESA", 6),
    ("MATERIAIS DE LIMPEZA E ALIMENTAÇÃO", "DESPESA", 6),
    ("GUIA DE CUSTAS PAGAS PARA O CLIENTE", "DESPESA", 6),
    ("CONFRATERNIZAÇÕES DO ESCRITÓRIO", "DESPESA", 6),
    ("COMBUSTÍVEL", "DESPESA", 6),
    ("EQUIPAMENTOS ELETRÔNICOS", "DESPESA", 6),
    ("PASSAGENS AÉREAS E RODOVIÁRIAS", "DESPESA", 6),
    ("ALARMES E SEGURANÇA", "DESPESA", 6),
    ("DEVOLUÇÃO APORTE DO SÓCIO", "DESPESA", 6),
    # DESPESA — grupo 7 (despesas bancárias).
    ("TAXAS BANCÁRIAS", "DESPESA", 7),
    ("JUROS BANCÁRIOS", "DESPESA", 7),
    # DESPESA — grupo 8 (marketing e comercial).
    ("MARKETING JURÍDICO E PUBLICIDADE", "DESPESA", 8),
    # DESPESA — grupo 9 (distribuição de lucros).
    ("DISTRIBUIÇÃO DE LUCROS", "DESPESA", 9),
]


def upgrade() -> None:
    op.execute("CREATE TYPE entry_type AS ENUM ('RECEITA', 'DESPESA')")

    op.create_table(
        "dre_groups",
        sa.Column("id", sa.SmallInteger(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "nature", postgresql.ENUM("RECEITA", "DESPESA", name="entry_type", create_type=False)
        ),
    )
    dre_groups_table = sa.table(
        "dre_groups",
        sa.column("id", sa.SmallInteger()),
        sa.column("name", sa.Text()),
        sa.column(
            "nature", postgresql.ENUM("RECEITA", "DESPESA", name="entry_type", create_type=False)
        ),
    )
    op.bulk_insert(
        dre_groups_table,
        [{"id": id_, "name": name, "nature": nature} for id_, name, nature in _DRE_GROUPS],
    )

    op.create_table(
        "financial_categories",
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
            "dre_group_id", sa.SmallInteger(), sa.ForeignKey("dre_groups.id"), nullable=False
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "type",
            postgresql.ENUM("RECEITA", "DESPESA", name="entry_type", create_type=False),
            nullable=False,
        ),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_fin_cat_type",
        "financial_categories",
        ["tenant_id", "type"],
        postgresql_where=sa.text("is_active"),
    )
    # unaccent na unicidade (regra 5) — mesma técnica de uq_stages_tenant_step_name (015).
    op.execute(
        "CREATE UNIQUE INDEX uq_fin_cat_tenant_name ON financial_categories "
        "(tenant_id, immutable_unaccent(lower(name)))"
    )
    for statement in enable_rls_statements("financial_categories"):
        op.execute(statement)

    op.create_table(
        "cost_centers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("name", sa.Text(), nullable=False),
        # Não está no esboço SQL da spec — necessário pra regra 8 ("GERAL não pode ser
        # excluído") não depender de comparar por nome (frágil a rename). Mesmo padrão
        # de financial_categories.is_default (achado ao implementar, ver Descobertas).
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_cost_centers_tenant_name ON cost_centers "
        "(tenant_id, immutable_unaccent(lower(name)))"
    )
    for statement in enable_rls_statements("cost_centers"):
        op.execute(statement)

    # Seed idempotente (só atinge tenants que já existem no momento da migration — mesma
    # limitação de 011/012/014/015, sem spec de provisionamento de tenant ainda).
    category_rows = ", ".join(
        f"('{name}', '{type_}', {group_id})" for name, type_, group_id in _CATEGORIES
    )
    op.execute(f"""
        INSERT INTO financial_categories (tenant_id, dre_group_id, name, type, is_default)
        SELECT t.id, v.dre_group_id, v.name, v.type::entry_type, true
        FROM tenants t
        CROSS JOIN (VALUES {category_rows}) AS v(name, type, dre_group_id)
        ON CONFLICT (tenant_id, immutable_unaccent(lower(name))) DO NOTHING
        """)
    op.execute("""
        INSERT INTO cost_centers (tenant_id, name, is_default)
        SELECT t.id, 'GERAL', true
        FROM tenants t
        ON CONFLICT (tenant_id, immutable_unaccent(lower(name))) DO NOTHING
        """)


def downgrade() -> None:
    op.drop_table("cost_centers")
    op.drop_table("financial_categories")
    op.drop_table("dre_groups")
    op.execute("DROP TYPE entry_type")
