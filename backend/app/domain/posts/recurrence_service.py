"""Ciclo de vida das séries de recorrência (spec 034).

Geração sempre avança a partir de `last_generated_date` (nunca da ocorrência
concluída), então a série é monotônica: concluir uma ocorrência atrasada depois que
o worker adiantou a série não volta no tempo, e a guarda `series_date_exists`
garante que conclusão (regra 1) e worker (regra 2) nunca criam a mesma data duas
vezes.
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dates import next_occurrence, preview_occurrences
from app.domain.posts.models import Post, PostRecurrence
from app.domain.posts.repository import PostRepository, RecurrenceRepository
from app.domain.posts.schemas import RecurrenceInput, RecurrenceUpdateRequest

# Teto defensivo do catch-up do worker — uma série diária abandonada há mais de um
# ano não explode em milhares de inserts numa única varredura; o worker do dia
# seguinte continua de onde parou.
_SWEEP_CATCH_UP_LIMIT = 366


class RecurrenceService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.posts = PostRepository(session)
        self.recurrences = RecurrenceRepository(session)

    async def create_series(self, post: Post, payload: RecurrenceInput) -> PostRecurrence:
        """O post criado junto é o template e a PRIMEIRA ocorrência da série."""
        recurrence = PostRecurrence(
            tenant_id=self.tenant_id,
            template_post_id=post.id,
            period=payload.period,
            repeat_on=payload.repeat_on,
            until_date=payload.until_date,
            max_occurrences=payload.max_occurrences,
            occurrences_created=1,
            last_generated_date=post.scheduled_date,
        )
        self.session.add(recurrence)
        await self.session.flush()
        post.recurrence_id = recurrence.id
        # O UPDATE dispara o onupdate server-side de posts.updated_at — sem valor
        # explícito o atributo expira e a leitura síncrona na resposta explode com
        # MissingGreenlet (mesma lição do PostService.update / LawsuitService.update).
        post.updated_at = datetime.now(UTC)
        await self.session.flush()
        return recurrence

    async def get_for_post(self, post: Post) -> PostRecurrence | None:
        return await self.recurrences.get_for_post(post)

    async def update_series(
        self, recurrence: PostRecurrence, payload: RecurrenceUpdateRequest
    ) -> PostRecurrence:
        """Regra 8: editar afeta só o futuro — occurrences_created,
        last_generated_date e as ocorrências já geradas não mudam."""
        recurrence.period = payload.period
        recurrence.repeat_on = payload.repeat_on
        recurrence.until_date = payload.until_date
        recurrence.max_occurrences = payload.max_occurrences
        await self.session.flush()
        return recurrence

    async def deactivate(self, recurrence: PostRecurrence) -> None:
        """DELETE /posts/{id}/recurrence — encerra a série (regra 7: preserva o já
        gerado; as ocorrências continuam posts independentes)."""
        recurrence.is_active = False
        await self.session.flush()

    async def preview(self, recurrence: PostRecurrence, *, count: int) -> list[date]:
        template = await self.posts.get_by_id(recurrence.template_post_id)
        if template is None or template.scheduled_date is None:
            return []
        return preview_occurrences(
            recurrence.period,
            recurrence.repeat_on,
            anchor=template.scheduled_date,
            start=recurrence.last_generated_date or template.scheduled_date,
            count=count,
            until_date=recurrence.until_date,
            max_occurrences=recurrence.max_occurrences,
            occurrences_created=recurrence.occurrences_created,
        )

    async def _template_if_running(self, recurrence: PostRecurrence) -> Post | None:
        """O post-modelo da série, ou `None` quando a série não deve gerar mais nada.

        Regra 6: o limite de ocorrências encerra a série pelo que vier primeiro — e
        encerrar significa DESLIGAR, não apenas devolver nada. Uma série que atingiu o teto
        e continua ativa seria consultada para sempre pelo worker.
        """
        if not recurrence.is_active:
            return None
        template = await self.posts.get_by_id(recurrence.template_post_id)
        # A busca do modelo vem ANTES do teto de propósito: série cujo modelo sumiu não é
        # desligada aqui. Desligar sem modelo mudaria o estado de uma série que nem chegou
        # a ser avaliada — e a ordem original é a que os testes da 034 exercitam.
        if template is None:
            return None
        if (
            recurrence.max_occurrences is not None
            and recurrence.occurrences_created >= recurrence.max_occurrences
        ):
            recurrence.is_active = False
            await self.session.flush()
            return None
        return template

    async def generate_next(self, recurrence: PostRecurrence) -> Post | None:
        """Gera a próxima ocorrência da série (regras 1, 2, 6, 9). Devolve None quando
        a série encerrou (limite atingido — regra 6) ou a data já existe (guarda de
        idempotência entre conclusão e worker)."""
        template = await self._template_if_running(recurrence)
        if template is None or template.scheduled_date is None:
            return None
        anchor = template.scheduled_date
        candidate = next_occurrence(
            recurrence.period,
            recurrence.repeat_on,
            anchor=anchor,
            current=recurrence.last_generated_date or anchor,
        )
        if recurrence.until_date is not None and candidate > recurrence.until_date:
            recurrence.is_active = False
            await self.session.flush()
            return None
        if await self.recurrences.series_date_exists(recurrence.id, candidate):
            return None
        # Os campos relativos (término, prazo fatal) andam pelo mesmo delta da data
        # do compromisso — o ciclo da tarefa se preserva entre ocorrências.
        delta = candidate - anchor
        post = Post(
            tenant_id=self.tenant_id,
            lawsuit_id=template.lawsuit_id,
            task_type_id=template.task_type_id,
            created_by=template.created_by,
            scheduled_date=candidate,
            scheduled_time=template.scheduled_time,
            end_date=template.end_date + delta if template.end_date is not None else None,
            end_time=template.end_time,
            deadline_date=(
                template.deadline_date + delta if template.deadline_date is not None else None
            ),
            all_day=template.all_day,
            location=template.location,
            comments=template.comments,
            # Regra 9: cada ocorrência é um post independente, com o SEU reward_snapshot
            # (copiado do template, que já estava congelado na criação — regra 3 da 032).
            reward_snapshot=template.reward_snapshot,
            is_important=template.is_important,
            is_urgent=template.is_urgent,
            is_future=template.is_future,
            is_private=template.is_private,
            show_in_schedule=template.show_in_schedule,
            recurrence_id=recurrence.id,
        )
        assignee_ids = await self.posts.assignee_ids_for(template.id)
        created = await self.posts.create_with_assignees(post, list(assignee_ids))
        recurrence.occurrences_created += 1
        recurrence.last_generated_date = candidate
        await self.session.flush()
        return created

    async def advance_on_completion(self, post: Post) -> Post | None:
        """Gatilho da regra 1: a próxima ocorrência nasce ao concluir a ATUAL — a
        mais recente gerada. Concluir uma atrasada (quando o worker já adiantou a
        série) não gera nada. O chamador só invoca quando TODOS os responsáveis
        concluíram (a tarefa como um todo fechou — regra 3 da 033)."""
        if post.recurrence_id is None:
            return None
        recurrence = await self.recurrences.get_by_id(post.recurrence_id)
        if recurrence is None or not recurrence.is_active:
            return None
        if post.scheduled_date != recurrence.last_generated_date:
            return None
        return await self.generate_next(recurrence)

    async def sweep_overdue(self, today: date) -> int:
        """Worker diário de segurança (regra 2): coloca em dia as séries ativas cuja
        última data gerada passou sem conclusão. Devolve quantas ocorrências gerou."""
        generated = 0
        for recurrence in await self.recurrences.list_overdue(today):
            for _ in range(_SWEEP_CATCH_UP_LIMIT):
                last = recurrence.last_generated_date
                if last is None or last >= today:
                    break
                if await self.generate_next(recurrence) is None:
                    break
                generated += 1
        return generated
