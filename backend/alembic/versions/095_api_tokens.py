"""API pública v1 — tokens e log de requisição

Revision ID: 095_api_tokens
Revises: 094_llm_decisions
Create Date: 2026-08-28

Spec 095. Duas tabelas, e as duas existem por causa de perguntas que aparecem depois:

- `api_tokens` guarda o HASH, nunca o token. O `prefix` existe porque a pergunta operacional
  é "qual token está fazendo isso?", e sem os primeiros caracteres a resposta seria um UUID
  que o integrador não reconhece.
- `api_requests` é o log. Retenção de 30 dias (regra 9), e é o que responde "por que meu
  script parou de funcionar às 3h da manhã?".

`token_hash` é UNIQUE global, sem tenant: dois escritórios com o mesmo token seria
exatamente a falha que a autenticação existe para impedir.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "095_api_tokens"
down_revision: str | None = "094_llm_decisions"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "api_tokens",
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
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("prefix", sa.Text(), nullable=False),
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("allowed_ips", postgresql.ARRAY(postgresql.INET()), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    for statement in enable_rls_statements("api_tokens"):
        op.execute(statement)
    # A autenticação procura pelo hash ANTES de saber o tenant — é o único caminho que
    # não pode depender do RLS, e por isso ele roda em `SECURITY DEFINER` (ver 079).
    op.execute("CREATE INDEX ix_api_tokens_hash ON api_tokens (token_hash)")
    op.execute("""
        CREATE OR REPLACE FUNCTION api_token_lookup(p_hash TEXT)
        RETURNS TABLE (
            id UUID,
            tenant_id UUID,
            scopes TEXT[],
            allowed_ips INET[],
            expires_at TIMESTAMPTZ,
            revoked_at TIMESTAMPTZ,
            created_by UUID
        )
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT id, tenant_id, scopes, allowed_ips, expires_at, revoked_at, created_by
            FROM api_tokens
            WHERE token_hash = p_hash
        $$;
        """)
    op.execute("REVOKE ALL ON FUNCTION api_token_lookup(TEXT) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION api_token_lookup(TEXT) TO rito_app")

    op.create_table(
        "api_requests",
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
            "token_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("api_tokens.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("status_code", sa.SmallInteger(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    for statement in enable_rls_statements("api_requests"):
        op.execute(statement)
    op.execute("CREATE INDEX ix_api_requests_token ON api_requests (token_id, created_at DESC)")


def downgrade() -> None:
    op.drop_table("api_requests")
    op.execute("DROP FUNCTION IF EXISTS api_token_lookup(TEXT)")
    op.drop_table("api_tokens")
