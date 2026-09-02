import base64
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, Row, Select, and_, func, literal, or_, select, union_all
from sqlalchemy.sql.selectable import Subquery

from app.core.repository import BaseRepository
from app.domain.action_groups.models import ActionGroup, LawsuitType
from app.domain.customers.models import Customer
from app.domain.lawsuits.models import (
    Lawsuit,
    LawsuitMovement,
    LawsuitParty,
    LawsuitStageHistory,
    LawsuitSubject,
    MovementOrigin,
    PartyPole,
    WorkflowApplication,
    WorkflowSuppression,
)
from app.domain.stages.models import Stage, Step
from app.domain.users.models import User

# Regra 5 (spec 047): a partir daqui um processo sai sozinho da fila — sem coluna de
# status dedicada, é o mesmo predicado do índice parcial ix_lawsuits_datajud_due.
DATAJUD_NOT_FOUND_PAUSE_THRESHOLD = 5


_MOVEMENT_KIND_BY_ORIGIN = {
    "movement_auto": MovementOrigin.TRIBUNAL,
    "movement_manual": MovementOrigin.MANUAL,
}


@dataclass
class TimelineRow:
    kind: str
    id: uuid.UUID
    occurred_at: datetime
    title: str
    summary: str | None
    actor: str | None
    header: str | None
    external_code: int | None


def encode_timeline_cursor(occurred_at: datetime, kind: str, id_: uuid.UUID) -> str:
    """Cursor opaco da timeline — codifica `(occurred_at, kind, id)`, as 3 chaves da
    ordenação estável (regra 1: timestamp, depois tipo, depois id)."""
    raw = json.dumps([occurred_at.isoformat(), kind, str(id_)], separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_timeline_cursor(cursor: str) -> tuple[datetime, str, uuid.UUID]:
    occurred_at, kind, id_str = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
    return datetime.fromisoformat(occurred_at), kind, uuid.UUID(id_str)


@dataclass
class DerivedRefs:
    """Grupo de ação e fase de um processo — os dois campos que a resposta de detalhe
    carrega e que não moram na tabela `lawsuits`."""

    action_group_id: uuid.UUID
    action_group_name: str
    step_id: int
    step_name: str


def _timeline_keyset(timeline: Any, cursor: tuple[datetime, str, uuid.UUID]) -> ColumnElement[bool]:
    """Predicado keyset da timeline, com as três chaves em ordem MISTA.

    `occurred_at DESC, kind ASC, id ASC` não cabe numa comparação de tupla — `(a, b, c) <
    (x, y, z)` só funciona quando todas as colunas vão na mesma direção. O predicado exato
    é o desdobramento lexicográfico: menor no primeiro campo, OU igual e maior no segundo,
    OU iguais os dois e maior no terceiro.

    Errar isso não quebra a primeira página; quebra a segunda, repetindo ou pulando linha.
    """
    cursor_at, cursor_kind, cursor_id = cursor
    return or_(
        timeline.c.occurred_at < cursor_at,
        and_(
            timeline.c.occurred_at == cursor_at,
            timeline.c.kind > cursor_kind,
        ),
        and_(
            timeline.c.occurred_at == cursor_at,
            timeline.c.kind == cursor_kind,
            timeline.c.id > cursor_id,
        ),
    )


def _timeline_row(row: Row[Any]) -> TimelineRow:
    """Um evento da timeline, lido por NOME — o UNION ALL nomeia todas as colunas.

    Por nome e não por posição justamente porque são várias fontes unidas: cada `SELECT` do
    UNION precisa declarar as mesmas colunas na mesma ordem, e ler por nome faz um erro
    nessa ordem virar `AttributeError` no teste em vez de campo trocado em produção.
    """
    return TimelineRow(
        kind=row.kind,
        id=row.id,
        occurred_at=row.occurred_at,
        title=row.title,
        summary=row.summary,
        actor=row.actor,
        header=row.header,
        external_code=row.external_code,
    )


class LawsuitRepository(BaseRepository[Lawsuit]):
    model = Lawsuit

    async def get_derived_refs(self, lawsuit: Lawsuit) -> DerivedRefs | None:
        """Spec 098, regra 6: os dois saltos numa query só.

        Antes eram quatro `session.get()` em sequência — tipo de ação, grupo, etapa,
        fase — e eles apareciam em TODA rota que carrega um processo, inclusive na
        timeline, que nem usa os campos derivados. Quatro round-trips ao banco por
        requisição, sempre pelas mesmas chaves primárias: é exatamente o N+1 que a
        regra 6 proíbe, só que escrito à mão em vez de emitido por lazy load.

        Não usa `joinedload` porque este domínio não declara `relationship()` — o acesso
        a dado é explícito por repositório. O JOIN explícito é a tradução direta.
        """
        stmt = (
            select(
                ActionGroup.id,
                ActionGroup.name,
                Step.id,
                Step.name,
            )
            .select_from(LawsuitType)
            .join(ActionGroup, ActionGroup.id == LawsuitType.action_group_id)
            .join(Stage, Stage.id == lawsuit.stage_id)
            .join(Step, Step.id == Stage.step_id)
            .where(LawsuitType.id == lawsuit.lawsuit_type_id)
        )
        row = (await self.session.execute(stmt)).first()
        if row is None:
            return None
        return DerivedRefs(
            action_group_id=row[0], action_group_name=row[1], step_id=row[2], step_name=row[3]
        )

    async def find_by_process_number_digits(self, digits: str) -> Sequence[Lawsuit]:
        """Casamento por número (spec 045, regra 9): compara só dígitos — o processo
        pode estar salvo com ou sem máscara CNJ."""
        stmt = select(Lawsuit).where(
            func.regexp_replace(Lawsuit.process_number, r"\D", "", "g") == digits
        )
        return (await self.session.scalars(stmt)).all()

    async def list_by_responsible(self, user_id: uuid.UUID) -> Sequence[Lawsuit]:
        """Candidatos da estratégia 2 de casamento (spec 045, §5) — processos do
        advogado identificado pelo termo monitorado que capturou a publicação."""
        stmt = select(Lawsuit).where(Lawsuit.user_id == user_id)
        return (await self.session.scalars(stmt)).all()

    async def list_by_ids(self, ids: Sequence[uuid.UUID]) -> Sequence[Lawsuit]:
        """Spec 051: base da ação em massa do Kanban (regra 9) — os processos do lote
        numa query só, RLS garante que só vêm os do tenant da sessão."""
        if not ids:
            return []
        stmt = select(Lawsuit).where(Lawsuit.id.in_(ids))
        return (await self.session.scalars(stmt)).all()

    async def list_due_for_datajud_sync(self, *, limit: int) -> Sequence[Lawsuit]:
        """Fila da sincronização (spec 047, §4/regra 1) — mesmo predicado do índice
        parcial `ix_lawsuits_datajud_due`: só processo com número, não arquivado, e
        que não estourou o teto de "não encontrado" (regra 5/9: lote, nunca tudo)."""
        stmt = (
            select(Lawsuit)
            .where(
                Lawsuit.process_number.is_not(None),
                Lawsuit.is_archived.is_(False),
                Lawsuit.datajud_not_found_count < DATAJUD_NOT_FOUND_PAUSE_THRESHOLD,
            )
            # Desempate OBRIGATÓRIO. `datajud_last_sync_at` é NULL para todo processo que
            # nunca sincronizou, e um `ORDER BY` que empata sob um `LIMIT` não é uma fila:
            # o Postgres pode devolver quaisquer `limit` linhas entre as empatadas, e as
            # mesmas de novo na volta seguinte. Com mais processos que o lote, um processo
            # podia nunca ser escolhido — fome, não lentidão.
            #
            # `created_at` é o critério justo (o mais antigo na fila primeiro) e `id` fecha
            # a ordem total. Achado na spec 124: até a migration 124 o `created_at` vinha de
            # `now()` e empatava dentro da transação, então nem ele desempatava — a ordem
            # era a física do heap, e um teste de sincronização passava por sorte.
            .order_by(
                Lawsuit.datajud_last_sync_at.asc().nulls_first(),
                Lawsuit.created_at.asc(),
                Lawsuit.id,
            )
            .limit(limit)
        )
        return (await self.session.scalars(stmt)).all()

    async def list_due_tenant_ids(self) -> Sequence[uuid.UUID]:
        """Quais tenants têm processo na fila (spec 047) — usado pela varredura
        cross-tenant do worker (mesmo padrão de `MonitoredTermRepository.list_due`
        na 044): a sessão de superusuário só descobre POR ONDE passar, cada tenant
        sincroniza na própria sessão com RLS de verdade."""
        stmt = (
            select(Lawsuit.tenant_id)
            .where(
                Lawsuit.process_number.is_not(None),
                Lawsuit.is_archived.is_(False),
                Lawsuit.datajud_not_found_count < DATAJUD_NOT_FOUND_PAUSE_THRESHOLD,
            )
            .distinct()
        )
        return (await self.session.scalars(stmt)).all()


class LawsuitPartyRepository(BaseRepository[LawsuitParty]):
    model = LawsuitParty

    async def list_for_lawsuit(self, lawsuit_id: uuid.UUID) -> Sequence[tuple[LawsuitParty, str]]:
        """Partes com o nome do contato, na ordem de exibição da regra 7:
        polo (ATIVO → PASSIVO → CONTRARIA → TERCEIRO — ordem natural do enum) e,
        dentro do polo, alfabética."""
        stmt = (
            select(LawsuitParty, Customer.name)
            .join(Customer, Customer.id == LawsuitParty.customer_id)
            .where(LawsuitParty.lawsuit_id == lawsuit_id)
            .order_by(LawsuitParty.pole, Customer.name)
        )
        result = await self.session.execute(stmt)
        return result.tuples().all()

    async def find_duplicate(
        self,
        *,
        lawsuit_id: uuid.UUID,
        customer_id: uuid.UUID,
        pole: PartyPole,
        exclude_id: uuid.UUID | None = None,
    ) -> LawsuitParty | None:
        stmt = select(LawsuitParty).where(
            LawsuitParty.lawsuit_id == lawsuit_id,
            LawsuitParty.customer_id == customer_id,
            LawsuitParty.pole == pole,
        )
        if exclude_id is not None:
            stmt = stmt.where(LawsuitParty.id != exclude_id)
        result = await self.session.scalars(stmt)
        return result.first()

    async def count_for_lawsuit(self, lawsuit_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(LawsuitParty)
            .where(LawsuitParty.lawsuit_id == lawsuit_id)
        )
        return await self.session.scalar(stmt) or 0


class LawsuitMovementRepository(BaseRepository[LawsuitMovement]):
    model = LawsuitMovement

    async def find_by_external_id(
        self, lawsuit_id: uuid.UUID, external_id: str
    ) -> LawsuitMovement | None:
        stmt = select(LawsuitMovement).where(
            LawsuitMovement.lawsuit_id == lawsuit_id,
            LawsuitMovement.external_id == external_id,
        )
        result = await self.session.scalars(stmt)
        return result.first()

    def _timeline_union(self, lawsuit_id: uuid.UUID, kinds: Sequence[str]) -> Subquery | None:
        sources: list[
            Select[tuple[uuid.UUID, datetime, str, str, str | None, str, str | None, int | None]]
        ] = []
        for kind in kinds:
            origin = _MOVEMENT_KIND_BY_ORIGIN.get(kind)
            if origin is None:
                continue  # slot sem fonte ainda (task/publication/transaction)
            sources.append(
                select(
                    LawsuitMovement.id,
                    LawsuitMovement.occurred_at,
                    literal(kind).label("kind"),
                    LawsuitMovement.title,
                    LawsuitMovement.body.label("summary"),
                    User.name.label("actor"),
                    LawsuitMovement.header,
                    LawsuitMovement.external_code,
                )
                .select_from(LawsuitMovement)
                .outerjoin(User, User.id == LawsuitMovement.created_by)
                .where(
                    LawsuitMovement.lawsuit_id == lawsuit_id,
                    LawsuitMovement.origin == origin,
                )
            )
        if not sources:
            return None
        return union_all(*sources).subquery()

    async def list_timeline(
        self,
        lawsuit_id: uuid.UUID,
        *,
        kinds: Sequence[str],
        cursor: tuple[datetime, str, uuid.UUID] | None,
        limit: int,
    ) -> tuple[Sequence[TimelineRow], int]:
        """Timeline unificada (spec 026): agregação por UNION ALL das fontes pedidas
        (regra 8 — nunca N+1), ordenação estável `occurred_at DESC, kind, id` (regra 1) e
        paginação keyset pelo mesmo trio (regra 6). Duas statements no total (página +
        contagem dos kinds, sem o filtro de cursor — `total` não muda entre páginas)."""
        sources = self._timeline_union(lawsuit_id, kinds)
        if sources is None:
            return [], 0

        timeline = sources
        # Spec 098, regra 1: o total vem por função de janela na MESMA query da página,
        # em vez de um `SELECT count(*)` separado. A contagem já era um `count` sobre o
        # mesmo UNION ALL — computá-la duas vezes custava dois planos idênticos, e o
        # orçamento de 3 queries da timeline não cabia com ela de fora.
        stmt = select(timeline, func.count().over().label("total"))
        if cursor is not None:
            stmt = stmt.where(_timeline_keyset(timeline, cursor))
        stmt = stmt.order_by(timeline.c.occurred_at.desc(), timeline.c.kind, timeline.c.id).limit(
            limit
        )
        rows = (await self.session.execute(stmt)).all()
        # Sem linhas na página não há janela para contar. `total = 0` é o valor certo:
        # a única forma de a página vir vazia é não haver o que paginar.
        total = rows[0].total if rows else 0
        return [_timeline_row(row) for row in rows], total


class LawsuitSubjectRepository(BaseRepository[LawsuitSubject]):
    model = LawsuitSubject

    async def existing_codes(self, lawsuit_id: uuid.UUID) -> set[int]:
        result = await self.session.scalars(
            select(LawsuitSubject.code).where(LawsuitSubject.lawsuit_id == lawsuit_id)
        )
        return set(result.all())


class LawsuitStageHistoryRepository(BaseRepository[LawsuitStageHistory]):
    model = LawsuitStageHistory


class WorkflowApplicationRepository(BaseRepository[WorkflowApplication]):
    model = WorkflowApplication

    async def list_for_lawsuit(self, lawsuit_id: uuid.UUID) -> Sequence[WorkflowApplication]:
        stmt = (
            select(WorkflowApplication)
            .where(WorkflowApplication.lawsuit_id == lawsuit_id)
            .order_by(WorkflowApplication.applied_at.desc())
        )
        return (await self.session.scalars(stmt)).all()

    async def latest_for(
        self, lawsuit_id: uuid.UUID, workflow_id: uuid.UUID
    ) -> WorkflowApplication | None:
        """Regra 8: base do "já aplicado, mostrando quando foi" — registro real, não a
        heurística de `WorkflowService._already_applied` (que existe só porque, antes
        desta spec, `Post` não tinha de onde vir essa informação)."""
        stmt = (
            select(WorkflowApplication)
            .where(
                WorkflowApplication.lawsuit_id == lawsuit_id,
                WorkflowApplication.workflow_id == workflow_id,
            )
            .order_by(WorkflowApplication.applied_at.desc())
            .limit(1)
        )
        return (await self.session.scalars(stmt)).first()


class WorkflowSuppressionRepository(BaseRepository[WorkflowSuppression]):
    model = WorkflowSuppression

    async def is_suppressed(self, lawsuit_id: uuid.UUID, stage_id: uuid.UUID) -> bool:
        stmt = select(WorkflowSuppression.id).where(
            WorkflowSuppression.lawsuit_id == lawsuit_id, WorkflowSuppression.stage_id == stage_id
        )
        return (await self.session.scalar(stmt)) is not None
