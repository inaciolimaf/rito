"""124: o relógio dos carimbos e o fuso do CHECK de pagamento (dívidas 31 e 32)

Revision ID: 124_relogio_e_fuso
Revises: 102_squads_unaccent
Create Date: 2026-09-02

## Parte 1 — `now()` vira `statement_timestamp()` (dívida 31)

`now()` do Postgres devolve o instante de **início da transação**, não o do statement. Desde
a spec 105 cada teste roda dentro de uma transação única, então todas as linhas criadas num
mesmo teste nasciam com `created_at` IDÊNTICO — por mais requisições HTTP separadas que as
tivessem criado. Empatado o valor de ordenação, `paginate_keyset` desempatava por UUID v4, e
`test_ordenacao_por_created_at_desc` virava cara ou coroa: falhava em metade das execuções no
HEAD limpo, e um PR que quebrasse a ordenação de verdade tinha 50% de chance de passar.

Medido contra o banco real, do jeito que a aplicação insere (um statement por comando, dentro
de uma transação): `now()` devolve valores iguais, `statement_timestamp()` devolve diferentes.

Os defaults são descobertos do CATÁLOGO, não listados à mão: são 105 colunas em 39 arquivos
de modelo, e uma lista literal aqui envelheceria na primeira tabela nova. O `DO` block varre
`information_schema` e troca só o que casa exatamente com `now()`.

## Parte 2 — o CHECK de pagamento sai (dívida 32, item 3)

`ck_tx_payment_not_future` compara `payment_date` com `CURRENT_DATE`, que é o dia do
**servidor**. Depois da spec 114 a aplicação recusa data futura no fuso do **escritório**. Por
até três horas por dia os dois discordam: são duas regras com o mesmo nome e respostas
diferentes.

Hoje isso não quebra escrita nenhuma, porque a aplicação é a mais restritiva das duas e
recusa antes. Mas é uma armadilha: a próxima pessoa a mexer vai assumir que concordam.

O CHECK **sai** em vez de virar uma regra com fuso. O banco não sabe de que escritório é a
linha — `transactions.tenant_id` existe, mas o fuso mora em `accounts`, e um CHECK não pode
consultar outra tabela. Uma regra de banco que não consegue ser correta é pior que nenhuma:
ela dá a impressão de que alguém está conferindo. Quem conta é a validação da aplicação, que
tem o fuso e é testada.
"""

from alembic import op

revision: str = "124_relogio_e_fuso"
down_revision: str | None = "102_squads_unaccent"
branch_labels: str | None = None
depends_on: str | None = None


# `pg_get_expr` devolve o texto do default. `now()` casa exato; `CURRENT_TIMESTAMP` é
# sinônimo e o Postgres o normaliza para `now()`, então uma comparação só cobre os dois.
_TROCA_DEFAULTS = """
DO $$
DECLARE
    coluna record;
BEGIN
    FOR coluna IN
        SELECT c.table_name, c.column_name
        FROM information_schema.columns c
        WHERE c.table_schema = 'public'
          AND c.column_default = '{de}'
    LOOP
        EXECUTE format(
            'ALTER TABLE public.%I ALTER COLUMN %I SET DEFAULT {para}',
            coluna.table_name, coluna.column_name
        );
    END LOOP;
END $$;
"""


def upgrade() -> None:
    op.execute(_TROCA_DEFAULTS.format(de="now()", para="statement_timestamp()"))
    # `IF EXISTS`: bancos criados antes da 056 não têm a constraint, e um deploy não pode
    # falhar por causa de algo que já não está lá.
    op.execute("ALTER TABLE transactions DROP CONSTRAINT IF EXISTS ck_tx_payment_not_future")


def downgrade() -> None:
    op.execute(_TROCA_DEFAULTS.format(de="statement_timestamp()", para="now()"))
    # Recriar o CHECK pode falhar se existir linha com `payment_date` futura no fuso do
    # servidor — que é exatamente o estado que ele passou a permitir. `NOT VALID` recria a
    # regra para escritas novas sem reprovar o passado, que é o que um downgrade deve fazer:
    # voltar o comportamento, não julgar o dado que existia enquanto ele estava fora.
    op.execute(
        "ALTER TABLE transactions ADD CONSTRAINT ck_tx_payment_not_future "
        "CHECK (payment_date IS NULL OR payment_date <= CURRENT_DATE) NOT VALID"
    )
