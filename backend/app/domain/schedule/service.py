import secrets
import uuid
from dataclasses import dataclass
from datetime import date, time, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import Text, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.invariants import not_none
from app.domain.account.models import DEFAULT_TIMEZONE
from app.domain.account.repository import AccountRepository
from app.domain.posts.models import Post
from app.domain.schedule.ical import ICalEvent
from app.domain.schedule.repository import ScheduleRepository

# Regra 8: a consulta da agenda é limitada a 90 dias por requisição.
MAX_RANGE_DAYS = 90
# Regra 5: o feed iCal cobre 12 meses para frente.
FEED_WINDOW_DAYS = 365
# Spec 137: e 90 dias para trás, não 365. A janela era simétrica, e o passado distante
# não serve a um calendário — ninguém abre o Google Agenda para ver o compromisso de
# outubro do ano passado. Metade dos 115.196 eventos medidos no feed estava atrás de
# hoje. Reduzir a janela é o corte que não perde nada de útil.
FEED_PAST_DAYS = 90
# Tetos de linhas (spec 137). Não são paginação: as duas rotas devolvem o intervalo
# inteiro de uma vez por contrato, e o teto é o que impede uma resposta de 20 MB.
# 5.000 compromissos em 90 dias são 55 por dia; 10.000 no feed de 15 meses são 22 por
# dia útil. Acima disso a tela deixa de ser uma agenda e vira um relatório.
MAX_SCHEDULE_EVENTS = 5_000
FEED_MAX_EVENTS = 10_000


class ScheduleStatus(StrEnum):
    """Regra 3 — cores da agenda."""

    PENDENTE = "PENDENTE"
    CONCLUIDA = "CONCLUIDA"
    ATRASADA = "ATRASADA"


class DateField(StrEnum):
    """Regra 2 — o eixo do calendário."""

    SCHEDULED = "scheduled"
    DEADLINE = "deadline"


class RangeTooLongError(Exception):
    """Intervalo acima de 90 dias — 422 (regra 8)."""


@dataclass
class SchedulePage:
    """A agenda de um intervalo, e se o teto de linhas cortou alguma coisa.

    `truncated` existe para a tela poder dizer ao usuário que ele não está vendo tudo:
    um teto silencioso é pior que nenhum teto, porque some com o compromisso sem avisar
    (spec 137)."""

    events: list["ScheduleEvent"]
    truncated: bool


@dataclass
class ScheduleEvent:
    post_id: uuid.UUID
    lawsuit_id: uuid.UUID
    task_type_name: str
    axis_date: date
    scheduled_date: date | None
    scheduled_time: time | None
    end_date: date | None
    end_time: time | None
    deadline_date: date | None
    all_day: bool
    location: str | None
    status: ScheduleStatus
    is_urgent: bool
    is_important: bool
    assignee_names: list[str]


# As colunas do `RETURNS TABLE` de `lookup_ical_feed` (migration 037).
COLUNAS_ICAL_FEED = ("tenant_id", "user_id")


async def resolve_feed_token(
    session: AsyncSession, token: str
) -> tuple[uuid.UUID, uuid.UUID] | None:
    """Resolve (tenant_id, user_id) pelo token público do feed.

    Única consulta cross-tenant do sistema fora do pré-auth: a função
    `lookup_ical_feed` é SECURITY DEFINER e expõe só o par de ids por match exato
    (ver migration 037_ical). Depois do resolve, a sessão seta o tenant e o RLS
    vale normalmente para todo o resto.
    """
    funcao = func.lookup_ical_feed(literal(token, Text())).table_valued(*COLUNAS_ICAL_FEED)
    row = (await session.execute(select(funcao))).first()
    if row is None:
        return None
    return (row.tenant_id, row.user_id)


def _hidden_from(post: Post, viewer: uuid.UUID, assignees: list[Any]) -> bool:
    """Regra 8 da spec 033, aplicada à agenda: tarefa privada de terceiro não vaza.

    Some da visão de quem não é criador nem responsável — inclusive do gestor. Privacidade
    de tarefa não tem exceção por perfil; se tivesse, não seria privacidade.
    """
    if not post.is_private or post.created_by == viewer:
        return False
    return all(viewer != uid for uid, _name, _done in assignees)


def _event_status(*, completed: bool, axis: date, today: date) -> ScheduleStatus:
    """Regra 3 — as cores da agenda. Concluída ganha de atrasada: uma tarefa entregue com
    atraso já foi entregue, e mostrá-la em vermelho seria cobrar o que está feito."""
    if completed:
        return ScheduleStatus.CONCLUIDA
    return ScheduleStatus.ATRASADA if axis < today else ScheduleStatus.PENDENTE


def _event(
    post: Post, task_type_name: str, axis: date, status: ScheduleStatus, assignees: list[Any]
) -> ScheduleEvent:
    """Um compromisso da agenda, com a data do EIXO escolhido em campo próprio.

    `axis_date` é o que a agenda posiciona; `scheduled_date` e `deadline_date` continuam nos
    seus campos. Os três porque a tela alterna o eixo (regra 2) e ainda mostra as duas datas
    no card — colapsá-los perderia justamente a informação de que o prazo é outro dia.
    """
    return ScheduleEvent(
        post_id=post.id,
        lawsuit_id=post.lawsuit_id,
        task_type_name=task_type_name,
        axis_date=axis,
        scheduled_date=post.scheduled_date,
        scheduled_time=post.scheduled_time,
        end_date=post.end_date,
        end_time=post.end_time,
        deadline_date=post.deadline_date,
        all_day=post.all_day,
        location=post.location,
        status=status,
        is_urgent=post.is_urgent,
        is_important=post.is_important,
        assignee_names=[name for _uid, name, _done in assignees],
    )


class ScheduleService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = ScheduleRepository(session)
        self.account = AccountRepository(session)

    async def feed_timezone(self) -> str:
        """Fuso em que o feed iCal escreve as datas (regra 5). Vinha lido no router
        direto do `AccountRepository` (spec 118, checagem 2)."""
        return await self.account.timezone() or DEFAULT_TIMEZONE

    async def list_events(
        self,
        *,
        viewer: uuid.UUID,
        start: date,
        end: date,
        date_field: DateField,
        user_id: uuid.UUID | None,
        show_completed: bool,
        today: date,
        limit: int = MAX_SCHEDULE_EVENTS,
    ) -> SchedulePage:
        if (end - start).days > MAX_RANGE_DAYS:
            raise RangeTooLongError("Intervalo máximo de consulta é de 90 dias.")
        # `limit + 1` é o mesmo idioma do keyset das listagens: a linha extra não vai
        # para a resposta, só responde "havia mais".
        rows = await self.repository.list_posts(
            start=start,
            end=end,
            date_field=date_field.value,
            user_id=user_id,
            limit=limit + 1,
        )
        truncated = len(rows) > limit
        rows = rows[:limit]
        lines = await self.repository.assignee_lines([post.id for post, _ in rows])
        events: list[ScheduleEvent] = []
        for post, task_type_name in rows:
            assignees = lines.get(post.id, [])
            if _hidden_from(post, viewer, assignees):
                continue
            completed = bool(assignees) and all(done for _uid, _name, done in assignees)
            if completed and not show_completed:
                continue
            axis = post.scheduled_date if date_field == DateField.SCHEDULED else post.deadline_date
            axis = not_none(axis, "o repositório já filtra eixo NULL")
            status = _event_status(completed=completed, axis=axis, today=today)
            events.append(_event(post, task_type_name, axis, status, assignees))
        return SchedulePage(events=events, truncated=truncated)

    async def feed_events(self, *, user_id: uuid.UUID, today: date) -> list[ICalEvent]:
        """Regra 5: só tarefas do usuário com `show_in_schedule`, 90 dias para trás e 12
        meses para frente, com teto de linhas. Eixo do feed é a data de compromisso (é o
        que faz sentido num calendário); o summary marca prazo fatal quando existir.

        A janela e o teto entraram na spec 137. A rota é pública por token, fora de
        `/api/v1`, sem sessão e sem rate limit, e clientes de calendário (Google, Outlook,
        Apple) fazem polling a cada 15 minutos POR USUÁRIO: cada feed ligado é carga fixa
        e recorrente. Medido antes: 115.196 eventos, 1,9 s de consulta, 0,6 s de montagem,
        19,8 MB de `.ics` por requisição."""
        rows = await self.repository.list_posts(
            start=today - timedelta(days=FEED_PAST_DAYS),
            end=today + timedelta(days=FEED_WINDOW_DAYS),
            date_field=DateField.SCHEDULED.value,
            user_id=user_id,
            limit=FEED_MAX_EVENTS,
        )
        return [
            ICalEvent(
                post_id=post.id,
                summary=(
                    f"[PRAZO] {task_type_name}"
                    if post.deadline_date is not None and post.deadline_date == post.scheduled_date
                    else task_type_name
                ),
                day=post.scheduled_date or today,
                start_time=None if post.all_day else post.scheduled_time,
                end_day=post.end_date,
                end_time=post.end_time,
                all_day=post.all_day,
                location=post.location,
            )
            for post, task_type_name in rows
        ]

    async def enable_ical(self, *, user_id: uuid.UUID) -> str:
        """Gera o token na primeira ativação e devolve o caminho do feed."""
        from app.domain.users.models import User

        user = await self.session.get(User, user_id)
        user = not_none(user, "o id vem do usuário autenticado")
        if not user.ical_token:
            user.ical_token = secrets.token_urlsafe(32)
        user.ical_enabled = True
        await self.session.flush()
        return f"/ical/{user.ical_token}.ics"

    async def regenerate_ical(self, *, user_id: uuid.UUID) -> str:
        """Regra 5: regenerar invalida o token anterior imediatamente."""
        from app.domain.users.models import User

        user = await self.session.get(User, user_id)
        user = not_none(user, "o id vem do usuário autenticado")
        user.ical_token = secrets.token_urlsafe(32)
        user.ical_enabled = True
        await self.session.flush()
        return f"/ical/{user.ical_token}.ics"
