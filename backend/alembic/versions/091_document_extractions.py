"""extração de documentos

Revision ID: 091_document_extractions
Revises: 090_ai_budget
Create Date: 2026-08-27

Spec 091: o arquivo sobe, o OCR lê, o modelo estrutura — e o resultado espera aqui até
alguém confirmar. A tabela guarda as três coisas que a revisão humana precisa ter à mão:
o texto cru do OCR (para conferir quando o valor parecer errado), os campos extraídos com
a confiança de cada um, e a correção que o humano fez.

`extracted` é JSONB de `{campo: {value, confidence}}` porque os campos mudam com o tipo do
documento — um RG tem nome e CPF, um contrato social tem razão social e CNPJ. Coluna por
campo viraria migração a cada tipo novo.

O índice parcial é a fila de trabalho: o que interessa listar é o que ainda está
esperando revisão, e ela é curta por definição.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "091_document_extractions"
down_revision: str | None = "090_ai_budget"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "document_extractions",
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
        # Nulo quando o arquivo entrou direto pela tela de extração: cadastrar um cliente
        # a partir do RG acontece ANTES de existir a que anexar o arquivo.
        sa.Column(
            "attachment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("attachments.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("document_kind", sa.Text(), nullable=True),
        sa.Column("ocr_text", sa.Text(), nullable=True),
        # Regra 1: saber se o OCR rodou é o que explica o custo e o tempo da extração.
        sa.Column("used_ocr", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "extracted",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        # Regra 6: o que o humano mudou é a métrica de qualidade da extração.
        sa.Column(
            "corrections",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("target_type", sa.Text(), nullable=True),
        sa.Column(
            "action_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_actions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("applied_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'reviewed', 'applied', 'discarded')",
            name="ck_document_extractions_status",
        ),
    )
    for statement in enable_rls_statements("document_extractions"):
        op.execute(statement)
    op.execute(
        "CREATE INDEX ix_extractions_pending ON document_extractions "
        "(tenant_id, created_at DESC) WHERE status = 'pending'"
    )


def downgrade() -> None:
    op.drop_table("document_extractions")
