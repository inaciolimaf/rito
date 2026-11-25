"""133: papel de banco só-leitura para o text-to-SQL da IA

Revision ID: 133_papel_de_leitura_da_ia
Revises: 126_prazo_das_intimacoes
Create Date: 2026-09-08

A quarta camada do §5 da spec 089 prometia que "mesmo que as três anteriores falhassem, a
conexão não consegue escrever". Ela cumpria a metade que dizia respeito a ESCRITA
(`transaction_read_only = on`) e não cumpria a que dizia respeito a LEITURA: `set_config`
não é escrita, e uma consulta do modelo que a chamasse trocava o `app.tenant_id` da sessão
no meio da própria consulta — as views barreira leem o GUC, e o InitPlan de um `OFFSET` é
avaliado antes delas. Resultado medido no HEAD: a sessão do escritório A recebia a linha do
escritório B.

Esta migration dá corpo à camada que faltava, no banco e não no texto:

1. **`rito_ai`** — papel `NOLOGIN`, `NOSUPERUSER`, `NOBYPASSRLS`, membro de nada. A única
   coisa que ele pode fazer neste banco é `SELECT` nas 9 relações do catálogo analítico da
   089. Ele não é um papel de conexão: `rito_app` assume-o com `SET LOCAL ROLE` dentro do
   savepoint em que a consulta do modelo roda, e o `ROLLBACK TO SAVEPOINT` o desfaz.

2. **`REVOKE EXECUTE ON set_config FROM PUBLIC`**, com `GRANT` de volta só para `rito_app`.
   É esta linha que torna o `app.tenant_id` IMUTÁVEL enquanto o papel corrente é `rito_ai`:
   sem `EXECUTE`, `set_config('app.tenant_id', …)` morre com *permission denied* na hora de
   avaliar o InitPlan, antes de qualquer linha ser lida. Fecha junto
   `set_config('role', 'rito_app', …)`, que seria o caminho de volta.

3. **`GRANT SELECT`** nas 9 relações do catálogo (mais as 5 tabelas que sustentam a única
   delas que é view viva — ver `_TABELAS_DE_APOIO`), e em nenhuma outra. A allowlist de
   relações, que até aqui só existia na análise estática do `sql_guard`, passa a existir
   também como privilégio: a tabela crua que escapasse do parser esbarra no
   `permission denied for table`.

Como a `rito_app` da migration 003, `rito_ai` é compartilhada pelo cluster e por isso não
é derrubada no downgrade — cada banco desfaz só os próprios `GRANT`s.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "133_papel_de_leitura_da_ia"
down_revision: str | None = "126_prazo_das_intimacoes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# As mesmas 9 de `app/domain/ai/sql_guard.py::ALLOWED_RELATIONS`. Escritas de novo aqui
# porque privilégio de banco não se importa de propósito: uma lista que o Python monta em
# tempo de migration esconderia, no dia em que alguém editasse a constante, que o `GRANT`
# de um banco já migrado não muda sozinho. O teste
# `test_ai_sql_role.py::test_o_papel_da_ia_le_exatamente_o_catalogo_da_allowlist` compara
# as duas listas e falha se divergirem.
_RELACOES = (
    "ai_allowed_metrics",
    "bi_pipeline_monthly_visible",
    "bi_vintage_visible",
    "bi_lawsuit_cycles_visible",
    "bi_cost_allocation_visible",
    "user_monthly_scores_visible",
    "account_daily_balances_visible",
    "agility_daily_visible",
    "timesheet_daily_visible",
)

# As tabelas que sustentam `ai_allowed_metrics`.
#
# Ela é a única das nove que NÃO é view barreira sobre matview: é uma view viva sobre
# `lawsuits`, criada com `security_invoker=true` na migration 089 justamente para que o RLS
# de quem consulta seja o que isola — o §4 do `CLAUDE.md` («quem garante é o RLS») aplicado
# a uma agregação em tempo real. Com `security_invoker`, o privilégio conferido é o do
# papel corrente, e por isso `rito_ai` precisa do `SELECT` nas cinco tabelas de baixo.
#
# Isso não afrouxa nada: `rito_ai` é `NOBYPASSRLS`, as políticas de `lawsuits`,
# `lawsuit_types`, `action_groups` e `stages` valem para ele exatamente como valem para
# `rito_app`, e o `sql_guard` continua recusando qualquer consulta que cite essas tabelas
# pelo nome. O que ele ganha é ler a view — e nada além do próprio escritório, porque o
# `app.tenant_id` que ele não pode trocar é o que a política lê.
_TABELAS_DE_APOIO = (
    "lawsuits",
    "lawsuit_types",
    "action_groups",
    "stages",
    "steps",
)

_CREATE_AI_ROLE = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'rito_ai') THEN
        CREATE ROLE rito_ai NOLOGIN
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
    END IF;
END
$$;
"""

_SET_CONFIG = "pg_catalog.set_config(text, text, boolean)"


def upgrade() -> None:
    op.execute(_CREATE_AI_ROLE)
    # `rito_app` precisa ser membro para poder assumir o papel; `NOINHERIT` na adesão
    # deixaria o `SET LOCAL ROLE` funcionar do mesmo jeito, mas herdar um papel que só lê
    # as 9 views não acrescenta nada ao que `rito_app` já pode.
    op.execute("GRANT rito_ai TO rito_app")
    op.execute("GRANT USAGE ON SCHEMA public TO rito_ai")
    for relacao in (*_RELACOES, *_TABELAS_DE_APOIO):
        op.execute(f'GRANT SELECT ON "{relacao}" TO rito_ai')
    op.execute(f"REVOKE EXECUTE ON FUNCTION {_SET_CONFIG} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_SET_CONFIG} TO rito_app")


def downgrade() -> None:
    op.execute(f"GRANT EXECUTE ON FUNCTION {_SET_CONFIG} TO PUBLIC")
    for relacao in (*_RELACOES, *_TABELAS_DE_APOIO):
        op.execute(f'REVOKE SELECT ON "{relacao}" FROM rito_ai')
    op.execute("REVOKE USAGE ON SCHEMA public FROM rito_ai")
    op.execute("REVOKE rito_ai FROM rito_app")
