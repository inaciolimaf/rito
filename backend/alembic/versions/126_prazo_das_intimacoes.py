"""126: prazo padrão de intimação do escritório + feriados nacionais de 2031 a 2040

Revision ID: 126_prazo_das_intimacoes
Revises: 124_relogio_e_fuso
Create Date: 2026-09-08

## Parte 1 — `publication_deadline_settings` (dívida 18)

A tarefa "Intimações Judiciais" da spec 045 nasce com `deadline_date` NULL desde 2026, e
a dívida 18 pede o cálculo. A conta é lei (arts. 219, 220 e 224 do CPC) e mora em
`app/core/dates.py`; o que faltava não era a conta, era **quantos dias**.

Este projeto não tem — e não vai ganhar aqui — tabela de prazo por classe/assunto do CNJ.
O levantamento do ADVBOX (`docs/ADVBOX-ESPECIFICACAO-COMPLETA.md`) também não tem: o único
lugar em que ele fala em prazo em dias é o `fake_days` da etapa de workflow (§3), que é um
número que o escritório digita. Então o número vem daqui: uma linha por tenant, com o que
o gestor declarou e o nome de quem declarou. Sem linha, ou com `default_deadline_days`
nulo, a tarefa continua nascendo sem prazo — que é a resposta honesta de quem não sabe.

Tabela de domínio: `tenant_id NOT NULL` + RLS, como manda o `CLAUDE.md` §4.

## Parte 2 — feriados nacionais de 2031 a 2040 (spec 038, descoberta 5)

O seed da 038 cobre 2026–2030 e a própria spec registrou que "em 2030+ a tabela precisa de
novo seed". Um prazo contado contra uma tabela vazia conta o feriado como dia útil e vence
antes da hora — é a falha mais silenciosa possível, porque o resultado continua sendo uma
data plausível.

Mesmo formato e mesma fonte da 038: os 9 fixos (Consciência Negra incluída, feriado
nacional desde a Lei 14.759/2023) e os 4 móveis derivados da Páscoa de cada ano — Carnaval
segunda (Páscoa −48) e terça (−47), Sexta-feira Santa (−2) e Corpus Christi (+60). As
datas foram conferidas contra as cinco que a 038 já tinha: batem exatamente.

**Isto também expira.** Em 2040 a tabela precisa do próximo seed, e a data em que ela
esvazia é 01/01/2041.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "126_prazo_das_intimacoes"
down_revision: str | None = "124_relogio_e_fuso"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FIRST_YEAR = 2031
_LAST_YEAR = 2040

# Cópia literal da lista da 038 — os feriados fixos não mudaram, e derivar a lista de lá
# por import acoplaria uma migration à outra, que é o que o `CLAUDE.md` §9 evita ao
# proibir editar migration commitada.
_FIXED_HOLIDAYS = [
    ("01-01", "Confraternização Universal"),
    ("04-21", "Tiradentes"),
    ("05-01", "Dia do Trabalho"),
    ("09-07", "Independência do Brasil"),
    ("10-12", "Nossa Senhora Aparecida"),
    ("11-02", "Finados"),
    ("11-15", "Proclamação da República"),
    ("11-20", "Dia Nacional de Zumbi e da Consciência Negra"),
    ("12-25", "Natal"),
]

# (ano, carnaval_seg, carnaval_ter, sexta_santa, corpus_christi) — da Páscoa do ano.
_MOVABLE_HOLIDAYS = {
    2031: ("02-24", "02-25", "04-11", "06-12"),  # Páscoa 13/04
    2032: ("02-09", "02-10", "03-26", "05-27"),  # Páscoa 28/03
    2033: ("02-28", "03-01", "04-15", "06-16"),  # Páscoa 17/04
    2034: ("02-20", "02-21", "04-07", "06-08"),  # Páscoa 09/04
    2035: ("02-05", "02-06", "03-23", "05-24"),  # Páscoa 25/03
    2036: ("02-25", "02-26", "04-11", "06-12"),  # Páscoa 13/04
    2037: ("02-16", "02-17", "04-03", "06-04"),  # Páscoa 05/04
    2038: ("03-08", "03-09", "04-23", "06-24"),  # Páscoa 25/04
    2039: ("02-21", "02-22", "04-08", "06-09"),  # Páscoa 10/04
    2040: ("02-13", "02-14", "03-30", "05-31"),  # Páscoa 01/04
}


def _seed_holidays() -> None:
    rows: list[str] = []
    for year in _MOVABLE_HOLIDAYS:
        for month_day, name in _FIXED_HOLIDAYS:
            rows.append(f"('{year}-{month_day}', '{name}', true)")
        carnival_mon, carnival_tue, good_friday, corpus = _MOVABLE_HOLIDAYS[year]
        rows.append(f"('{year}-{carnival_mon}', 'Carnaval', true)")
        rows.append(f"('{year}-{carnival_tue}', 'Carnaval', true)")
        rows.append(f"('{year}-{good_friday}', 'Sexta-feira Santa', true)")
        rows.append(f"('{year}-{corpus}', 'Corpus Christi', true)")
    # `ON CONFLICT DO NOTHING` é a diferença para a 038: se um dia destes anos já tiver
    # sido semeado à mão num banco existente, o boot não pode quebrar por causa disso.
    op.execute(
        f"INSERT INTO holidays (date, name, is_national) VALUES {', '.join(rows)} "
        "ON CONFLICT (date) DO NOTHING"
    )


def upgrade() -> None:
    op.create_table(
        "publication_deadline_settings",
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
        # Nulo = o escritório não declarou prazo. É o padrão, e é o estado em que toda
        # intimação continua nascendo sem `deadline_date`.
        sa.Column("default_deadline_days", sa.SmallInteger(), nullable=True),
        sa.Column(
            "count_in_business_days",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "updated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.statement_timestamp(),
        ),
        sa.UniqueConstraint("tenant_id", name="uq_pub_deadline_settings_tenant"),
        sa.CheckConstraint(
            "default_deadline_days IS NULL OR default_deadline_days BETWEEN 1 AND 365",
            name="ck_pub_deadline_days_range",
        ),
    )
    # Regra 4 da spec 098: toda FK com índice que a cubra. A tabela tem no máximo uma
    # linha por escritório, então o índice não é para leitura — é para o DELETE em
    # `users` não varrer a tabela inteira procurando referência.
    op.create_index(
        "ix_pub_deadline_settings_updated_by",
        "publication_deadline_settings",
        ["updated_by"],
    )
    # `enable_rls_statements` já cria o índice de `tenant_id` (mesmo padrão de toda
    # tabela de domínio desde a 003) — não há um segundo aqui.
    for statement in enable_rls_statements("publication_deadline_settings"):
        op.execute(statement)

    _seed_holidays()


def downgrade() -> None:
    # Só os anos que ESTA migration semeou — um seed futuro (2041+) não é dela para desfazer.
    op.execute(
        f"DELETE FROM holidays WHERE date >= '{_FIRST_YEAR}-01-01' "
        f"AND date <= '{_LAST_YEAR}-12-31'"
    )
    op.drop_index("ix_pub_deadline_settings_updated_by", table_name="publication_deadline_settings")
    op.drop_table("publication_deadline_settings")
