"""Board Kanban do CRM (spec 051) — leitura do board/coluna e mudança de fase.

Serviço próprio, fora de `LawsuitService` — mesmo padrão de `PartiesService`/
`MovementsService` (spec 030, "um service por caso de uso"). `change_stage` é o
único caminho que grava `lawsuit_stage_history` (regra 5); `LawsuitService.update`
(spec 022, PUT /lawsuits/{id}) também passa por aqui para que uma troca de etapa
"fora do Kanban" grave o mesmo histórico. `stage_entered_at` nunca é escrita à
mão — quem mantém é a trigger `trg_lawsuits_stage_entered_at` (migration 051).
"""

import dataclasses
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import Cache
from app.core.repository import decode_cursor, encode_cursor
from app.domain.automations.engine import AutomationEngine
from app.domain.automations.models import TriggerKind
from app.domain.lawsuits.exceptions import (
    LawsuitNotFoundError,
    NotResponsibleForLawsuitError,
    StageNotFoundError,
)
from app.domain.lawsuits.listing import (
    BOARD_DEFAULT_LIMIT_PER_COLUMN,
    BOARD_TOTAL_REFINE_THRESHOLD,
    BoardCardRow,
    CrmStatsRow,
    LawsuitFilters,
    LawsuitListingRepository,
)
from app.domain.lawsuits.models import Lawsuit, LawsuitStageHistory
from app.domain.lawsuits.repository import LawsuitRepository, LawsuitStageHistoryRepository
from app.domain.stages.repository import StageRepository
from app.domain.users.models import User, UserRole


@dataclass
class BoardData:
    cards_by_step: dict[int, list[BoardCardRow]]
    counts_by_step: dict[int, int]
    total: int
    suggest_refine: bool  # regra 11: sugestão, nunca bloqueia


@dataclass
class BoardColumnPage:
    items: list[BoardCardRow]
    next_cursor: str | None
    total: int


def _no_filter(filters: LawsuitFilters) -> bool:
    """Board padrão: nenhum filtro ativo. `dataclasses.asdict` não serve porque
    `LawsuitFilters` guarda listas; comparar campo a campo com o vazio é o que diz se
    esta é a visão que todo mundo abre."""
    vazio = LawsuitFilters()
    return all(
        getattr(filters, campo.name) == getattr(vazio, campo.name)
        for campo in dataclasses.fields(filters)
    )


def _move_to_stage(lawsuit: Lawsuit, to_stage_id: uuid.UUID) -> None:
    """Põe o processo na etapa nova e zera o relógio de estagnação.

    `updated_at` recebe valor EXPLÍCITO mesmo tendo `onupdate=CRIADO_EM` (server-side):
    sem ele, o autoflush de uma query seguinte expira o atributo, e relê-lo fora de um
    `await` — na serialização da resposta — estoura `MissingGreenlet`. Mesmo motivo
    documentado em `LawsuitService.update`.

    Spec 052, regra 4: mover reseta o relógio da etapa (o trigger cuida de
    `stage_entered_at`). Zero dia na etapa nova nunca é estagnação, então zera direto em vez
    de rodar `StagnationService.recalculate_stage` por uma query a mais.
    """
    lawsuit.stage_id = to_stage_id
    lawsuit.updated_at = datetime.now(UTC)
    lawsuit.is_stagnant = False
    lawsuit.stagnant_since = None


class BoardService:
    def __init__(
        self, session: AsyncSession, tenant_id: uuid.UUID, *, cache: Cache | None = None
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        # `cache` continua na assinatura porque os três chamadores do router de CRM o
        # passam, mas o board não guarda mais nada: ver `get_board` (spec 137).
        self.cache = cache
        self.listing = LawsuitListingRepository(session)
        self.lawsuits = LawsuitRepository(session)
        self.stages = StageRepository(session)
        self.history = LawsuitStageHistoryRepository(session)

    async def get_board(
        self, *, filters: LawsuitFilters, limit_per_column: int = BOARD_DEFAULT_LIMIT_PER_COLUMN
    ) -> BoardData:
        """Regra 1: as 9 fases, sempre todas — `counts_by_step`/`cards_by_step` só têm
        chave pra fase com processo; o chamador (schema/frontend) completa com zero/
        lista vazia as que faltam, sem uma 3ª query.

        ## O contador não é mais cacheado (spec 137)

        A visão sem filtro guardava `counts_by_step` em `crm:board_counts` por 5 minutos
        (spec 098, regra 9), e a chave só caía em `_invalidate_board_counts` — isto é, ao
        ARRASTAR um card. Criar processo, arquivar processo e trocar a etapa pelo PUT do
        detalhe não derrubavam nada, e o board mostrava o número velho pelo TTL inteiro.
        Medido: com 1 processo no escritório, criar o segundo mantinha `total = 1`;
        excluir o único também mantinha `total = 1`.

        A correção não é acrescentar mais um lugar que se lembra de invalidar — é tirar
        do cache o agregado que depende de escrita de OUTRO agregado. O que se paga por
        isso está medido: 14,9 ms de `GROUP BY` em 20 mil processos, uma vez por abertura
        do quadro, contra um contador que ficava errado por cinco minutos justamente
        depois da ação que o usuário acabou de fazer. A contagem de queries da rota não
        muda no caminho frio (5, o teto do §11); o caminho quente sai de 4 para 5.
        """
        counts = await self.listing.board_counts(filters=filters)
        cards = await self.listing.board(filters=filters, limit_per_column=limit_per_column)
        total = sum(counts.values())
        return BoardData(
            cards_by_step=cards,
            counts_by_step=counts,
            total=total,
            suggest_refine=total > BOARD_TOTAL_REFINE_THRESHOLD,
        )

    async def get_board_column(
        self, *, filters: LawsuitFilters, step_id: int, cursor: str | None, limit: int
    ) -> BoardColumnPage:
        decoded: tuple[datetime, uuid.UUID] | None = None
        if cursor:
            raw_value, cursor_id = decode_cursor(cursor)
            decoded = (datetime.fromisoformat(raw_value), cursor_id)
        items, total = await self.listing.board_column(
            filters=filters, step_id=step_id, cursor=decoded, limit=limit
        )
        next_cursor = None
        if len(items) == limit:
            last = items[-1].lawsuit
            next_cursor = encode_cursor(last.stage_entered_at.isoformat(), last.id)
        return BoardColumnPage(items=list(items), next_cursor=next_cursor, total=total)

    async def get_stats(self, *, filters: LawsuitFilters) -> CrmStatsRow:
        return await self.listing.crm_stats(filters=filters)

    async def move_stage(self, lawsuit: Lawsuit, *, stage_id: uuid.UUID, actor: User) -> Lawsuit:
        """Regras 3/5/10: move para a etapa exata pedida (o front já resolveu "primeira
        etapa da fase destino" — regra 3 — antes de chamar); Colaborador só move o que
        é seu; grava histórico."""
        if actor.role is UserRole.COLABORADOR and lawsuit.user_id != actor.id:
            raise NotResponsibleForLawsuitError
        if await self.stages.get_by_id(stage_id) is None:
            raise StageNotFoundError
        await self.change_stage(lawsuit, to_stage_id=stage_id, changed_by=actor.id)
        return lawsuit

    async def bulk_move_stage(
        self, lawsuit_ids: list[uuid.UUID], *, stage_id: uuid.UUID, actor: User
    ) -> int:
        """Regra 9: transacional — valida TUDO (etapa, existência, permissão) antes de
        mudar qualquer processo; um erro no meio derruba o lote inteiro, sem mudança
        parcial (o commit é do chamador — a request inteira é uma transação)."""
        if await self.stages.get_by_id(stage_id) is None:
            raise StageNotFoundError
        lawsuits = list(await self.lawsuits.list_by_ids(lawsuit_ids))
        found_ids = {lawsuit.id for lawsuit in lawsuits}
        if set(lawsuit_ids) - found_ids:
            raise LawsuitNotFoundError
        if actor.role is UserRole.COLABORADOR and any(
            lawsuit.user_id != actor.id for lawsuit in lawsuits
        ):
            raise NotResponsibleForLawsuitError
        for lawsuit in lawsuits:
            await self.change_stage(lawsuit, to_stage_id=stage_id, changed_by=actor.id)
        return len(lawsuits)

    async def _emit_stage_changed(
        self, lawsuit: Lawsuit, to_stage_id: uuid.UUID, from_stage_id: uuid.UUID | None
    ) -> None:
        """Spec 092: o gatilho vive AQUI, e não no router.

        Pelo mesmo motivo que o histórico vive aqui — mudar de etapa por fora do Kanban é
        mudar de etapa, e uma automação que só disparasse pelo arrasto do card perderia
        metade dos movimentos reais do escritório.
        """
        await AutomationEngine(self.session, self.tenant_id).emit(
            TriggerKind.LAWSUIT_STAGE_CHANGED.value,
            payload={
                "lawsuit_id": str(lawsuit.id),
                "stage_id": str(to_stage_id),
                "from_stage_id": str(from_stage_id) if from_stage_id else None,
                "lawsuit_type_id": str(lawsuit.lawsuit_type_id),
            },
            subject_type="lawsuit",
            subject_id=lawsuit.id,
        )

    async def change_stage(
        self, lawsuit: Lawsuit, *, to_stage_id: uuid.UUID, changed_by: uuid.UUID
    ) -> None:
        """Único caminho que grava `lawsuit_stage_history` — `LawsuitService.update`
        chama isto em vez de atribuir `stage_id` direto, pra "fora do Kanban" (regra 5)
        também gerar histórico."""
        if lawsuit.stage_id == to_stage_id:
            return
        anterior = lawsuit.stage_id
        await self.history.create(
            LawsuitStageHistory(
                tenant_id=self.tenant_id,
                lawsuit_id=lawsuit.id,
                from_stage_id=lawsuit.stage_id,
                to_stage_id=to_stage_id,
                changed_by=changed_by,
            )
        )
        _move_to_stage(lawsuit, to_stage_id)
        await self._emit_stage_changed(lawsuit, to_stage_id, anterior)
