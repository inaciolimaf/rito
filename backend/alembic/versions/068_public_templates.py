"""public_templates (spec 068 — Biblioteca pública de modelos)

Revision ID: 068_public_templates
Revises: 070_documents_templates_indexes
Create Date: 2026-08-13

O número da spec (068) é menor que o da migration anterior na cadeia (070) porque a
refatoração 070 foi antecipada nesta sessão para recuperar orçamento de suíte antes
de reabrir a fase 6 com mais teste novo (ver Descobertas da 067/070) — a ordem real
de aplicação das migrations é 067 (sem schema) → 070 → 068, não a ordem numérica das
specs.

Global e imutável, sem `tenant_id`/RLS — mesmo padrão de `courts`/`occupations`/
`dre_groups`. Seed de 6 modelos de exemplo (2 contratos, 2 petições, 1 recurso, 1
documento), conteúdo real o bastante para servir de ponto de partida (regra 2:
"copiar" clona isto para um `Template` editável do tenant).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "068_public_templates"
down_revision: str | None = "070_documents_templates_indexes"
branch_labels: str | None = None
depends_on: str | None = None

_PUBLIC_TEMPLATES: list[tuple[str, str, str]] = [
    (
        "Contrato de honorários advocatícios",
        "CONTRATO",
        "<h2>CONTRATO DE PRESTAÇÃO DE SERVIÇOS ADVOCATÍCIOS</h2>"
        "<p>Pelo presente instrumento particular, de um lado o(a) CONTRATANTE e, de "
        "outro lado, o(a) CONTRATADO(A), advogado(a) inscrito(a) na OAB, ajustam entre "
        "si o presente contrato de honorários advocatícios, mediante as cláusulas e "
        "condições a seguir descritas.</p>"
        "<h3>Cláusula 1ª — Do objeto</h3><p>O(A) CONTRATADO(A) prestará serviços de "
        "assessoria e representação jurídica ao(à) CONTRATANTE.</p>"
        "<h3>Cláusula 2ª — Dos honorários</h3><p>Pelos serviços prestados, o(a) "
        "CONTRATANTE pagará ao(à) CONTRATADO(A) os honorários ajustados entre as "
        "partes.</p>",
    ),
    (
        "Contrato de honorários — êxito",
        "CONTRATO",
        "<h2>CONTRATO DE HONORÁRIOS AD ÊXITO</h2>"
        "<p>As partes abaixo identificadas ajustam a prestação de serviços "
        "advocatícios com honorários vinculados ao resultado da demanda, nos termos "
        "das cláusulas seguintes.</p>"
        "<h3>Cláusula 1ª</h3><p>Os honorários de êxito corresponderão a percentual "
        "sobre o proveito econômico obtido, a ser ajustado entre as partes.</p>",
    ),
    (
        "Petição inicial cível",
        "PETICAO",
        "<h2>EXCELENTÍSSIMO(A) SENHOR(A) DOUTOR(A) JUIZ(A) DE DIREITO</h2>"
        "<p><strong>Qualificação das partes</strong></p>"
        "<p>Vem, respeitosamente, à presença de Vossa Excelência, propor a presente "
        "<strong>AÇÃO</strong>, pelos fatos e fundamentos a seguir expostos.</p>"
        "<h3>Dos fatos</h3><p>[Descrição dos fatos.]</p>"
        "<h3>Do direito</h3><p>[Fundamentação jurídica.]</p>"
        "<h3>Dos pedidos</h3><p>Ante o exposto, requer a procedência dos pedidos.</p>",
    ),
    (
        "Petição de juntada de documentos",
        "PETICAO",
        "<h2>EXCELENTÍSSIMO(A) SENHOR(A) DOUTOR(A) JUIZ(A) DE DIREITO</h2>"
        "<p>Nos autos do processo em epígrafe, vem requerer a juntada dos documentos "
        "anexos, para os devidos fins de direito.</p>"
        "<p>Nestes termos, pede deferimento.</p>",
    ),
    (
        "Recurso de apelação",
        "RECURSO",
        "<h2>RAZÕES DE APELAÇÃO</h2>"
        "<p><strong>Apelante:</strong> [nome] · <strong>Apelado:</strong> [nome]</p>"
        "<h3>Da tempestividade</h3><p>O presente recurso é tempestivo, nos termos do "
        "art. 1.003 do CPC.</p>"
        "<h3>Das razões recursais</h3><p>[Fundamentos do inconformismo com a decisão "
        "recorrida.]</p>"
        "<h3>Do pedido</h3><p>Requer o conhecimento e provimento do presente recurso.</p>",
    ),
    (
        "Procuração ad judicia",
        "DOCUMENTO",
        "<h2>PROCURAÇÃO</h2>"
        "<p><strong>OUTORGANTE:</strong> [nome, qualificação]</p>"
        "<p><strong>OUTORGADO(A):</strong> [nome do(a) advogado(a), OAB]</p>"
        "<p>Pelo presente instrumento, o(a) OUTORGANTE nomeia e constitui seu(sua) "
        "bastante procurador(a) o(a) OUTORGADO(A), a quem confere amplos poderes para "
        "o foro em geral, com a cláusula <em>ad judicia et extra</em>, podendo "
        "substabelecer.</p>",
    ),
]


def upgrade() -> None:
    op.create_table(
        "public_templates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "type",
            postgresql.ENUM(
                "CONTRATO",
                "PETICAO",
                "RECURSO",
                "DOCUMENTO",
                name="template_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("header_content", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("footer_content", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("watermark_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    public_templates_table = sa.table(
        "public_templates",
        sa.column("name", sa.Text()),
        sa.column(
            "type",
            postgresql.ENUM(
                "CONTRATO",
                "PETICAO",
                "RECURSO",
                "DOCUMENTO",
                name="template_type",
                create_type=False,
            ),
        ),
        sa.column("content", sa.Text()),
    )
    op.bulk_insert(
        public_templates_table,
        [
            {"name": name, "type": type_, "content": content}
            for name, type_, content in _PUBLIC_TEMPLATES
        ],
    )


def downgrade() -> None:
    op.drop_table("public_templates")
