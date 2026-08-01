"""steps stages

Revision ID: 015_steps_stages
Revises: 014_action_groups_types
Create Date: 2026-08-01

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.rls import enable_rls_statements

revision: str = "015_steps_stages"
down_revision: str | None = "014_action_groups_types"
branch_labels: str | None = None
depends_on: str | None = None

# docs/ADVBOX-ESPECIFICACAO-COMPLETA.md §3.1 — 9 fases fixas, nesta ordem (vira a coluna
# `position`, e a ordem das colunas do Kanban da spec 051).
_STEPS = [
    "Marketing",
    "Negociação",
    "Consultoria",
    "Administrativo",
    "Judicial",
    "Recursal",
    "Execução/cobrança",
    "Rh/financeiro",
    "Arquivamento",
]

# docs/ADVBOX-ESPECIFICACAO-COMPLETA.md §3.2 lista as 59 etapas como uma lista FLAT, sem
# declarar a qual fase cada uma pertence. O pareamento abaixo é inferência (spec 015,
# Descobertas): a lista fonte aparece em blocos contíguos e tematicamente coerentes — cada
# bloco foi lido como uma fase. Note que "PLANEJAMENTO" aparece 2x na fonte (Negociação e
# Marketing) — por isso o índice único de nome é por (tenant, fase), não só por tenant.
_STAGES_BY_STEP = [
    # Negociação (9) — funil de captação até o fechamento do contrato.
    ("ANÁLISE DO CASO", "Negociação"),
    ("AGUARDANDO DOCUMENTOS", "Negociação"),
    ("APRESENTAÇÃO DE PROPOSTA", "Negociação"),
    ("AGENDAR CONSULTA", "Negociação"),
    ("COBRANÇA INICIAL", "Negociação"),
    ("DEFINIÇÃO DE INTERESSES", "Negociação"),
    ("ELABORAÇÃO DE PARECER JURÍDICO", "Negociação"),
    ("FECHAMENTO", "Negociação"),
    ("PLANEJAMENTO", "Negociação"),
    # Administrativo (9) — tramitação perante órgão público.
    ("AGENDADO ATENDIMENTO NO ÓRGÃO", "Administrativo"),
    ("REQUERIMENTO PROTOCOLADO", "Administrativo"),
    ("ATENDENDO EXIGÊNCIAS", "Administrativo"),
    ("AGUARDANDO DECISÃO DO ÓRGÃO", "Administrativo"),
    ("DECISÃO PROFERIDA", "Administrativo"),
    ("RECURSO ADMINISTRATIVO PROTOCOLADO", "Administrativo"),
    ("AGUARDANDO DECISÃO DO RECURSO", "Administrativo"),
    ("DECISÃO DO RECURSO PROFERIDA", "Administrativo"),
    ("AGUARDANDO CÓPIA DO PROCESSO ADMINISTRATIVO", "Administrativo"),
    # Judicial (8) — ação judicial até o trânsito em julgado.
    ("DESENVOLVENDO INICIAL DE AÇÃO JUDICIAL", "Judicial"),
    ("AÇÃO PROTOCOLADA/INICIADA", "Judicial"),
    ("COM JUIZ(A) PARA ANÁLISE", "Judicial"),
    ("AGUARDANDO MANIFESTAÇÃO DA PARTE CONTRÁRIA", "Judicial"),
    ("AGUARDANDO AUDIÊNCIA", "Judicial"),
    ("AGUARDANDO JULGAMENTO", "Judicial"),
    ("SENTENÇA PROFERIDA", "Judicial"),
    ("TRANSITO EM JULGADO/PROCESSO FINALIZADO", "Judicial"),
    # Recursal (7) — recursos.
    ("DESENVOLVENDO RECURSO", "Recursal"),
    ("RECURSO PROTOCOLADO/INICIADO", "Recursal"),
    ("APRESENTADA RESPOSTA A RECURSO DA PARTE CONTRÁRIA (CONTRARRAZÕES)", "Recursal"),
    ("AGUARDANDO JULGAMENTO DO RECURSO", "Recursal"),
    ("RECURSO JULGADO", "Recursal"),
    ("TRANSITO EM JULGADO/NÃO CABE MAIS RECURSO", "Recursal"),
    ("DESENVOLVENDO RECURSO AOS TRIBUNAIS SUPERIORES", "Recursal"),
    # Execução/cobrança (11).
    ("ELABORAÇÃO DE CÁLCULO", "Execução/cobrança"),
    ("CITAÇÃO DO DEVEDOR PARA PAGAMENTO", "Execução/cobrança"),
    ("AGUARDANDO PENHORA", "Execução/cobrança"),
    ("AGUARDANDO JULGAMENTO DA EXECUÇÃO", "Execução/cobrança"),
    ("EXECUÇÃO JULGADA", "Execução/cobrança"),
    ("APRESENTADO RECURSO", "Execução/cobrança"),
    ("RESPOSTA A RECURSO", "Execução/cobrança"),
    ("AGUARDANDO SENTENÇA DE LIQUIDAÇÃO", "Execução/cobrança"),
    ("AGUARDANDO DECISÃO DO TRIBUNAL", "Execução/cobrança"),
    ("RPV EMITIDO", "Execução/cobrança"),
    ("AGUARDANDO PAGAMENTO DE CONDENAÇÃO", "Execução/cobrança"),
    # Consultoria (5).
    ("ELABORAÇÃO DE CONTRATO", "Consultoria"),
    ("ELABORAÇÃO DE PARECER", "Consultoria"),
    ("ENVIADA NOTIFICAÇÃO EXTRAJUDICIAL", "Consultoria"),
    ("ELABORAÇÃO DE TERMO DE ACORDO", "Consultoria"),
    ("AGENDADA REUNIÃO DE COMPOSIÇÃO DE ACORDO", "Consultoria"),
    # Rh/financeiro (1).
    ("PROCESSO RH PENDENTE", "Rh/financeiro"),
    # Arquivamento (4).
    ("ANALISADO E NÃO DISTRIBUÍDO", "Arquivamento"),
    ("ARQUIVADO POR DESINTERESSE CLIENTE", "Arquivamento"),
    ("ARQUIVADO POR DETERMINAÇÃO JUDICIAL", "Arquivamento"),
    ("ARQUIVADO/ENCERRADO", "Arquivamento"),
    # Marketing (5).
    ("ANÁLISE DE RESULTADOS", "Marketing"),
    ("PLANEJAMENTO", "Marketing"),
    ("PRODUÇÃO", "Marketing"),
    ("PROMOÇÃO", "Marketing"),
    ("RELACIONAMENTO", "Marketing"),
]


def upgrade() -> None:
    op.create_table(
        "steps",
        sa.Column("id", sa.SmallInteger(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("position", sa.SmallInteger(), nullable=False, unique=True),
    )
    steps_table = sa.table(
        "steps",
        sa.column("id", sa.SmallInteger()),
        sa.column("name", sa.Text()),
        sa.column("position", sa.SmallInteger()),
    )
    op.bulk_insert(
        steps_table,
        [
            {"id": index, "name": name, "position": index}
            for index, name in enumerate(_STEPS, start=1)
        ],
    )

    op.create_table(
        "stages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("step_id", sa.SmallInteger(), sa.ForeignKey("steps.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "enable_stagnant_days", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("stagnant_days", sa.Integer(), nullable=True),
        # FK real chega na spec 038, quando a tabela workflows existir.
        sa.Column("suggested_workflow_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "NOT enable_stagnant_days OR stagnant_days > 0", name="ck_stages_stagnant_days"
        ),
    )
    op.create_index("ix_stages_step", "stages", ["step_id"])
    # Substitui o UNIQUE(tenant_id, name) simples da seção 4 da spec: a fonte real tem
    # "PLANEJAMENTO" repetido em duas fases distintas (Negociação e Marketing) — a
    # unicidade certa é por (tenant, fase), não só por tenant. immutable_unaccent() já
    # existe desde a migration 014 (mesma função, reaproveitada).
    op.execute(
        "CREATE UNIQUE INDEX uq_stages_tenant_step_name ON stages "
        "(tenant_id, step_id, immutable_unaccent(lower(name)))"
    )
    for statement in enable_rls_statements("stages"):
        op.execute(statement)

    # Seed idempotente (só atinge tenants que já existem no momento da migration — mesma
    # limitação de 011/012/014, sem spec de provisionamento de tenant ainda).
    # Regra 5: "position dentro da fase" — o contador reinicia a cada fase, não é global.
    _positions_by_step: dict[str, int] = {}
    stage_rows: list[str] = []
    for name, step_name in _STAGES_BY_STEP:
        _positions_by_step[step_name] = _positions_by_step.get(step_name, 0) + 1
        stage_rows.append(f"('{name}', '{step_name}', {_positions_by_step[step_name]})")
    stage_values = ", ".join(stage_rows)
    op.execute(f"""
        INSERT INTO stages (tenant_id, step_id, name, position)
        SELECT t.id, s.id, v.name, v.position
        FROM tenants t
        CROSS JOIN (VALUES {stage_values}) AS v(name, step_name, position)
        JOIN steps s ON s.name = v.step_name
        ON CONFLICT (tenant_id, step_id, immutable_unaccent(lower(name))) DO NOTHING
        """)


def downgrade() -> None:
    op.drop_table("stages")
    op.drop_table("steps")
