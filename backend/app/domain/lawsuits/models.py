import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY as PGARRAY
from sqlalchemy.dialects.postgresql import ENUM as PGENUM
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import CRIADO_EM, Base, TenantMixin
from app.domain.courts.models import Court, CourtSystem


class ContingencyLevel(StrEnum):
    """Nível de contingenciamento (spec 024) — insumo de BI, sem cálculo aqui (regra 6)."""

    PROVAVEL = "PROVAVEL"
    POSSIVEL = "POSSIVEL"
    REMOTA = "REMOTA"


class LawsuitOutcome(StrEnum):
    """Resultado do processo (spec 024) — só é aceito com `closure_date` (regra 4)."""

    GANHO = "GANHO"
    PERDIDO = "PERDIDO"
    ACORDO = "ACORDO"


class Lawsuit(TenantMixin, Base):
    """Processo — entidade central do sistema (spec 022). Judicial, administrativo,
    consultivo ou de prospecção, diferenciado pela fase (`stage_id` → `step_id`) em que
    está. `action_group_id`/`step_id` são derivados (regra 2) e nunca residem aqui."""

    __tablename__ = "lawsuits"
    __table_args__ = (
        CheckConstraint("folder IS NULL OR length(folder) <= 30", name="ck_lawsuits_folder_length"),
        CheckConstraint(
            "fees_percentage IS NULL OR fees_percentage BETWEEN 0 AND 100", name="ck_fees_pct"
        ),
        # Regra 3: fechamento ≤ trânsito em julgado ≤ arquivamento.
        CheckConstraint(
            "(transit_date IS NULL OR closure_date IS NULL OR transit_date >= closure_date) "
            "AND (archived_date IS NULL OR transit_date IS NULL OR archived_date >= transit_date)",
            name="ck_cycle",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    lawsuit_type_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("lawsuit_types.id")
    )
    stage_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("stages.id"))
    # ForeignKey(Court.id)/(CourtSystem.id) em vez de string "courts.id" — `Court`/
    # `CourtSystem` vivem em `CourtBase`, uma `MetaData` própria (spec 021), então a
    # resolução por string (que só busca na `MetaData` da própria tabela, `Base.metadata`)
    # não encontra a tabela alvo; passar a coluna real resolve sem depender de qual
    # `MetaData` cada uma pertence.
    court_id: Mapped[int | None] = mapped_column(SmallInteger(), ForeignKey(Court.id), default=None)
    court_system_id: Mapped[int | None] = mapped_column(
        SmallInteger(), ForeignKey(CourtSystem.id), default=None
    )
    process_number: Mapped[str | None] = mapped_column(default=None)
    protocol_number: Mapped[str | None] = mapped_column(default=None)
    originating_process: Mapped[str | None] = mapped_column(default=None)
    folder: Mapped[str | None] = mapped_column(default=None)
    filing_year: Mapped[int | None] = mapped_column(SmallInteger(), default=None)
    judiciary: Mapped[str | None] = mapped_column(default=None)
    county: Mapped[str | None] = mapped_column(default=None)
    court_division: Mapped[str | None] = mapped_column(default=None)
    process_date: Mapped[date | None] = mapped_column(default=None)
    notes: Mapped[str | None] = mapped_column(default=None)
    # Honorários e ciclo de vida (spec 024) — base de todo o BI das specs 074–077.
    case_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)
    fees_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)
    fees_percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), default=None)
    contingency: Mapped[ContingencyLevel | None] = mapped_column(
        PGENUM(ContingencyLevel, name="contingency_level", create_type=False), default=None
    )
    closure_date: Mapped[date | None] = mapped_column(default=None)
    transit_date: Mapped[date | None] = mapped_column(default=None)
    archived_date: Mapped[date | None] = mapped_column(default=None)
    outcome: Mapped[LawsuitOutcome | None] = mapped_column(
        PGENUM(LawsuitOutcome, name="lawsuit_outcome", create_type=False), default=None
    )
    # Materializado pela trigger trg_movements_last_movement (migration 027) — nunca
    # escrito pela aplicação; serve às visões moved_*/idle_* da listagem.
    last_movement_at: Mapped[datetime | None] = mapped_column(default=None)
    is_archived: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    # Sincronização DataJud (spec 047, §5). `datajud_not_found_count` é o mecanismo de
    # pausa (regra 5) — sem coluna de status: ao chegar em 5 (ou de propósito em caso de
    # sigilo, regra 4), o processo sai sozinho da condição de `ix_lawsuits_datajud_due`.
    # As 4 últimas só a sync escreve, e só quando vazias (regra 8) — nenhum schema de
    # criação/edição do processo as aceita do cliente.
    datajud_last_sync_at: Mapped[datetime | None] = mapped_column(default=None)
    datajud_last_update: Mapped[datetime | None] = mapped_column(default=None)
    datajud_not_found_count: Mapped[int] = mapped_column(
        SmallInteger(), default=0, server_default=text("0")
    )
    judging_organ: Mapped[str | None] = mapped_column(default=None)
    filing_date: Mapped[date | None] = mapped_column(default=None)
    cnj_class_code: Mapped[int | None] = mapped_column(default=None)
    cnj_class_name: Mapped[str | None] = mapped_column(default=None)
    # Mantida pela trigger trg_lawsuits_stage_entered_at (migration 051) — nunca escrita
    # pela aplicação; base do "tempo na etapa" do card do Kanban (spec 051, regra 2) e
    # da estagnação (052).
    stage_entered_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)
    # Escritas só por StagnationService (spec 052) — mover processo (na hora, regra 4),
    # job diário às 3h e troca de `stagnant_days` da etapa (regra 10). Nunca via trigger:
    # a regra depende de `stages.enable_stagnant_days`/`stagnant_days`, de outra tabela.
    is_stagnant: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    stagnant_since: Mapped[date | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)
    updated_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM, onupdate=CRIADO_EM)


class PartyPole(StrEnum):
    """Polo que a parte ocupa no processo (spec 023). A ordem de declaração é a ordem de
    exibição (regra 7) — o enum Postgres replica esta ordem, então `ORDER BY pole` basta."""

    ATIVO = "ATIVO"
    PASSIVO = "PASSIVO"
    CONTRARIA = "CONTRARIA"
    TERCEIRO = "TERCEIRO"


class LawsuitParty(TenantMixin, Base):
    """Parte do processo (spec 023) — N:N entre processo e contato com o polo.
    `is_client` separa quem é cliente do escritório de parte contrária (regra 3).
    Delete do processo é cascade; delete do contato nunca (regra 5)."""

    __tablename__ = "lawsuit_parties"
    __table_args__ = (
        UniqueConstraint("lawsuit_id", "customer_id", "pole", name="uq_parties_lawsuit_pole"),
    )

    lawsuit_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("lawsuits.id", ondelete="CASCADE")
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("customers.id"))
    # `create_type=False`: o tipo é criado pela migration 023 — o SQLAlchemy não deve
    # tentar emitir CREATE TYPE num `create_all` de metadados (testes unitários puros).
    pole: Mapped[PartyPole] = mapped_column(PGENUM(PartyPole, name="party_pole", create_type=False))
    is_client: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)


class MovementOrigin(StrEnum):
    """Origem da movimentação (spec 026): TRIBUNAL vem da sync DataJud (spec 047) e é
    imutável pela UI (regra 3); MANUAL é editável/excluível pelo autor ou ADMINISTRADOR
    (regra 4)."""

    TRIBUNAL = "TRIBUNAL"
    MANUAL = "MANUAL"


class LawsuitMovement(TenantMixin, Base):
    """Movimentação do processo (spec 026) — manual ou automática. `external_id` é a
    chave de dedupe da sync DataJud (regra 5): reprocessar não duplica."""

    __tablename__ = "lawsuit_movements"
    __table_args__ = (
        UniqueConstraint("tenant_id", "lawsuit_id", "external_id", name="uq_movements_external"),
    )

    lawsuit_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("lawsuits.id", ondelete="CASCADE")
    )
    origin: Mapped[MovementOrigin] = mapped_column(
        PGENUM(MovementOrigin, name="movement_origin", create_type=False)
    )
    occurred_at: Mapped[datetime]
    title: Mapped[str]
    body: Mapped[str | None] = mapped_column(default=None)
    header: Mapped[str | None] = mapped_column(default=None)
    external_code: Mapped[int | None] = mapped_column(default=None)
    external_id: Mapped[str | None] = mapped_column(default=None)
    raw_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB(), default=None)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)


class LawsuitSubject(TenantMixin, Base):
    """Assunto do processo conforme a TPU (spec 047 §4) — a sync só insere; nunca
    remove um assunto que o CNJ parou de listar (mesmo espírito "nunca apaga" das
    outras integrações CNJ)."""

    __tablename__ = "lawsuit_subjects"
    __table_args__ = (UniqueConstraint("lawsuit_id", "code", name="uq_lawsuit_subjects_code"),)

    lawsuit_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("lawsuits.id", ondelete="CASCADE")
    )
    code: Mapped[int]
    name: Mapped[str]


class LawsuitStageHistory(TenantMixin, Base):
    """Histórico de mudança de etapa (spec 051, regra 5) — gravado pela aplicação
    (`LawsuitService`) toda vez que `stage_id` muda, Kanban ou não; `stage_entered_at`
    em `Lawsuit` é quem o trigger mantém sozinho (`changed_by` exige saber quem mudou,
    informação que uma trigger de banco não tem)."""

    __tablename__ = "lawsuit_stage_history"
    __table_args__ = (Index("ix_stage_history", "lawsuit_id", "changed_at"),)

    lawsuit_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("lawsuits.id", ondelete="CASCADE")
    )
    from_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("stages.id")
    )
    to_stage_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("stages.id"))
    changed_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)


class WorkflowApplication(TenantMixin, Base):
    """Registro do que um workflow criou num processo (spec 053, regra 4) — a única
    forma de saber quais posts desfazer (regra 5), já que `Post` não guarda vínculo
    com o workflow que o gerou (mesma limitação documentada em
    `WorkflowService._already_applied`, spec 038)."""

    __tablename__ = "workflow_applications"
    __table_args__ = (Index("ix_wf_app_lawsuit", "lawsuit_id", "applied_at"),)

    workflow_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("workflows.id"))
    lawsuit_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("lawsuits.id", ondelete="CASCADE")
    )
    # NULL = aplicado manualmente, fora do gatilho de mover etapa (regra 1 sugere,
    # nunca aplica sozinho — toda aplicação passa por confirmação humana).
    stage_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("stages.id"), default=None
    )
    applied_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    posts_created: Mapped[list[uuid.UUID]] = mapped_column(
        PGARRAY(PGUUID(as_uuid=True)), default=list, server_default=text("'{}'")
    )
    applied_at: Mapped[datetime] = mapped_column(server_default=CRIADO_EM)


class WorkflowSuppression(TenantMixin, Base):
    """ "Não sugerir novamente" (spec 053, regra 6) para o par processo+etapa. PK
    surrogate padrão de `Base` (a spec descreve PK composta lawsuit_id+stage_id, mas
    toda tabela do projeto usa o `id` UUID de `Base` sem exceção — o UNIQUE abaixo
    cumpre a mesma regra de "1 supressão por par")."""

    __tablename__ = "workflow_suppressions"
    __table_args__ = (
        UniqueConstraint("lawsuit_id", "stage_id", name="uq_workflow_suppressions_lawsuit_stage"),
    )

    lawsuit_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("lawsuits.id", ondelete="CASCADE")
    )
    stage_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("stages.id"))
