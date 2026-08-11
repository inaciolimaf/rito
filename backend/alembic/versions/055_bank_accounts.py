"""financial_institutions + bank_accounts (spec 055 — Financeiro: contas e cartões)

Revision ID: 055_bank_accounts
Revises: 054_chart_of_accounts
Create Date: 2026-08-11

`financial_institutions` é global (como `dre_groups`/`steps`) — seed completo, sem a
limitação de "só tenants que já existiam" (não é por tenant). Fonte: BrasilAPI
(`GET /api/banks/v1`, espelha o COMPE do Banco Central) filtrada para instituições com
"BCO"/"BANCO"/"CAIXA" no nome + os 6 maiores bancos digitais cujo nome oficial não usa
essas palavras (Nubank, PagBank, PicPay, Mercado Pago, Neon, Stone) — 129 instituições
reais, perto do "~95" da spec (aproximado, não é um número exato — ver Descobertas).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "055_bank_accounts"
down_revision: str | None = "054_chart_of_accounts"
branch_labels: str | None = None
depends_on: str | None = None

# (compe_code, name) — ver docstring acima pra origem dos dados.
_INSTITUTIONS: list[tuple[int, str]] = [
    (1, "BCO DO BRASIL S.A."),
    (3, "BCO DA AMAZONIA S.A."),
    (4, "BCO DO NORDESTE DO BRASIL S.A."),
    (12, "BANCO INBURSA"),
    (14, "STATE STREET BR S.A. BCO COMERCIAL"),
    (17, "BNY MELLON BCO S.A."),
    (18, "BCO TRICURY S.A."),
    (21, "BCO BANESTES S.A."),
    (24, "BCO BANDEPE S.A."),
    (25, "BCO ALFA S.A."),
    (33, "BCO SANTANDER (BRASIL) S.A."),
    (36, "BCO BBI S.A."),
    (37, "BCO DO EST. DO PA S.A."),
    (40, "BCO CARGILL S.A."),
    (41, "BCO DO ESTADO DO RS S.A."),
    (47, "BCO DO EST. DE SE S.A."),
    (63, "BANCO BRADESCARD"),
    (65, "BCO ANDBANK S.A."),
    (66, "BCO MORGAN STANLEY S.A."),
    (69, "BCO CREFISA S.A."),
    (70, "BRB - BCO DE BRASILIA S.A."),
    (74, "BCO. J.SAFRA S.A."),
    (75, "BANCO ABN AMRO CLEARING S.A."),
    (76, "BCO KDB BRASIL S.A."),
    (77, "BANCO INTER"),
    (79, "PICPAY BANK - BANCO MÚLTIPLO S.A"),
    (81, "BANCOSEGURO S.A."),
    (82, "BANCO TOPÁZIO S.A."),
    (83, "BCO DA CHINA BRASIL S.A."),
    (88, "BANCO RANDON S.A."),
    (94, "BANCO FINAXIS"),
    (95, "BANCO TRAVELEX S.A."),
    (96, "BCO B3 S.A."),
    (104, "CAIXA ECONOMICA FEDERAL"),
    (107, "BCO BOCOM BBM S.A."),
    (119, "BCO WESTERN UNION"),
    (120, "BCO RODOBENS S.A."),
    (121, "BCO AGIBANK S.A."),
    (122, "BCO BRADESCO BERJ S.A."),
    (124, "BCO WOORI BANK DO BRASIL S.A."),
    (125, "BANCO GENIAL"),
    (128, "BRAZA BANK S.A. BCO DE CÂMBIO"),
    (143, "INTEX BANK BCO DE CÂMBIO S.A."),
    (144, "EBURY BCO DE CÂMBIO S.A."),
    (197, "STONE IP S.A."),
    (208, "BANCO BTG PACTUAL S.A."),
    (212, "BANCO ORIGINAL"),
    (213, "BCO ARBI S.A."),
    (217, "BANCO JOHN DEERE S.A."),
    (218, "BCO BS2 S.A."),
    (222, "BCO CRÉDIT AGRICOLE BR S.A."),
    (224, "BCO FIBRA S.A."),
    (233, "BANCO BMG SOLUÇÕES FINANCEIRAS S.A."),
    (237, "BCO BRADESCO S.A."),
    (241, "BCO CLASSICO S.A."),
    (246, "BCO ABC BRASIL S.A."),
    (249, "BANCO INVESTCRED UNIBANCO S.A."),
    (250, "BANCO BMG CONSIGNADO S.A."),
    (254, "PARANA BCO S.A."),
    (259, "MONEYCORP BCO DE CÂMBIO S.A."),
    (260, "NU PAGAMENTOS - IP"),
    (265, "BCO FATOR S.A."),
    (266, "BCO CEDULA S.A."),
    (269, "BCO HSBC S.A."),
    (276, "BCO SENFF S.A."),
    (290, "PAGSEGURO INTERNET IP S.A."),
    (299, "BCO AFINZ S.A. - BM"),
    (300, "BCO LA NACION ARGENTINA"),
    (318, "BCO BMG S.A."),
    (323, "MERCADO PAGO IP LTDA."),
    (330, "BANCO BARI S.A."),
    (334, "BANCO BESA S.A."),
    (335, "BANCO DIGIO"),
    (336, "BCO C6 S.A."),
    (341, "ITAÚ UNIBANCO S.A."),
    (348, "BCO XP S.A."),
    (366, "BCO SOCIETE GENERALE BRASIL"),
    (368, "BCO CSF S.A."),
    (370, "BCO MIZUHO S.A."),
    (376, "BCO J.P. MORGAN S.A."),
    (378, "BCO BRASILEIRO DE CRÉDITO S.A."),
    (380, "PICPAY"),
    (381, "BCO MERCEDES-BENZ S.A."),
    (387, "BCO TOYOTA DO BRASIL S.A."),
    (389, "BCO MERCANTIL DO BRASIL S.A."),
    (390, "BCO GM S.A."),
    (393, "BCO VOLKSWAGEN S.A"),
    (394, "BCO BRADESCO FINANC. S.A."),
    (413, "BCO BV S.A."),
    (415, "BCO NACIONAL"),
    (422, "BCO SAFRA S.A."),
    (456, "BCO MUFG BRASIL S.A."),
    (464, "BCO SUMITOMO MITSUI BRASIL S.A."),
    (473, "BCO CAIXA GERAL BRASIL S.A."),
    (475, "BCO YAMAHA MOTOR S.A."),
    (479, "BCO ITAUBANK S.A."),
    (487, "DEUTSCHE BANK S.A.BCO ALEMAO"),
    (495, "BCO LA PROVINCIA B AIRES BCE"),
    (505, "BCO UBS BRASIL"),
    (536, "NEON PAGAMENTOS S.A. IP"),
    (554, "BCO STONEX S.A."),
    (600, "BCO LUSO BRASILEIRO S.A."),
    (604, "BCO INDUSTRIAL DO BRASIL S.A."),
    (610, "BCO VR S.A."),
    (611, "BCO PAULISTA S.A."),
    (612, "BCO GUANABARA S.A."),
    (613, "OMNI BANCO S.A."),
    (623, "BANCO PAN"),
    (626, "BCO C6 CONSIG"),
    (633, "BCO RENDIMENTO S.A."),
    (634, "BCO TRIANGULO S.A."),
    (637, "BCO SOFISA S.A."),
    (643, "BCO PINE S.A."),
    (654, "BCO DIGIMAIS S.A."),
    (655, "BCO VOTORANTIM S.A."),
    (707, "BCO DAYCOVAL S.A"),
    (708, "BCO INDUSCRED DE INVESTIM. S/A"),
    (720, "BCO RNX S.A."),
    (741, "BCO RIBEIRAO PRETO S.A."),
    (743, "BANCO SEMEAR"),
    (745, "BCO CITIBANK S.A."),
    (747, "BCO RABOBANK INTL BRASIL S.A."),
    (748, "BCO COOPERATIVO SICREDI S.A."),
    (752, "BCO BNP PARIBAS BRASIL S A"),
    (753, "NOVO BCO CONTINENTAL S.A. - BM"),
    (754, "BANCO SISTEMA"),
    (756, "BANCO SICOOB S.A."),
    (757, "BCO KEB HANA DO BRASIL S.A."),
    (795, "BANCO TRATON BRASIL S.A."),
]


def upgrade() -> None:
    op.execute(
        "CREATE TYPE account_kind AS ENUM "
        "('CORRENTE', 'POUPANCA', 'INVESTIMENTO', 'CARTAO_CREDITO', 'OUTRO')"
    )

    op.create_table(
        "financial_institutions",
        sa.Column("id", sa.SmallInteger(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("compe_code", sa.Text(), nullable=True),
    )
    institutions_table = sa.table(
        "financial_institutions",
        sa.column("id", sa.SmallInteger()),
        sa.column("name", sa.Text()),
        sa.column("compe_code", sa.Text()),
    )
    op.bulk_insert(
        institutions_table,
        [
            {"id": code, "name": name, "compe_code": str(code).zfill(3)}
            for code, name in _INSTITUTIONS
        ],
    )

    op.create_table(
        "bank_accounts",
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
            "kind",
            postgresql.ENUM(
                "CORRENTE",
                "POUPANCA",
                "INVESTIMENTO",
                "CARTAO_CREDITO",
                "OUTRO",
                name="account_kind",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "institution_id",
            sa.SmallInteger(),
            sa.ForeignKey("financial_institutions.id"),
            nullable=True,
        ),
        sa.Column("agency", sa.Text(), nullable=True),
        sa.Column("account_number", sa.Text(), nullable=True),
        sa.Column("cycle_day", sa.SmallInteger(), nullable=True),
        sa.Column("due_day", sa.SmallInteger(), nullable=True),
        sa.Column("initial_amount", sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_bank_accounts_tenant_name"),
        sa.CheckConstraint(
            "kind <> 'CARTAO_CREDITO' OR (cycle_day BETWEEN 1 AND 31 AND due_day BETWEEN 1 AND 31)",
            name="ck_bank_accounts_card_needs_cycle",
        ),
        sa.CheckConstraint(
            "kind = 'CARTAO_CREDITO' OR (cycle_day IS NULL AND due_day IS NULL)",
            name="ck_bank_accounts_non_card_no_cycle",
        ),
    )
    # Regra 2: 1 conta padrão ativa por tenant — garantido no banco, não na aplicação.
    op.execute(
        "CREATE UNIQUE INDEX ux_accounts_default ON bank_accounts (tenant_id) "
        "WHERE is_default AND is_active"
    )
    for statement in enable_rls_statements("bank_accounts"):
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("bank_accounts")
    op.drop_table("financial_institutions")
    op.execute("DROP TYPE account_kind")
