import uuid
from datetime import date, time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import UserRole, require_role
from app.core.rls import set_tenant_context
from app.domain.account.repository import AccountRepository
from app.domain.auth.deps import get_session_for_current_user
from app.domain.schedule.ical import build_ical
from app.domain.schedule.service import (
    DateField,
    RangeTooLongError,
    ScheduleService,
    ScheduleStatus,
    resolve_feed_token,
)
from app.domain.users.models import User

router = APIRouter(tags=["schedule"])
ical_router = APIRouter(tags=["ical"])

_NOT_FOUND_DETAIL = "Feed não encontrado ou desativado."


class ScheduleEventResponse(BaseModel):
    post_id: uuid.UUID
    lawsuit_id: uuid.UUID
    task_type_name: str
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
    # Por último: o campo `date` sombreia o tipo `date` para as anotações seguintes
    # na classe (mypy valid-type).
    date: date


class ScheduleListResponse(BaseModel):
    items: list[ScheduleEventResponse]


class ICalStatusResponse(BaseModel):
    enabled: bool
    url: str | None


class ICalEnableResponse(BaseModel):
    enabled: bool
    url: str


@router.get("/schedule", response_model=ScheduleListResponse)
async def list_schedule(
    from_: date = Query(alias="from"),
    to: date = Query(),
    user_id: uuid.UUID | None = Query(default=None),
    date_field: DateField = Query(default=DateField.SCHEDULED),
    show_completed: bool = Query(default=True),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> ScheduleListResponse:
    """Agenda (spec 037): só tarefas com `show_in_schedule` (regra 1), eixo alternável
    entre compromisso e prazo fatal (regra 2), intervalo máximo de 90 dias (regra 8)."""
    if to < from_:
        raise HTTPException(status_code=422, detail="Data final anterior à inicial.")
    service = ScheduleService(session)
    try:
        events = await service.list_events(
            viewer=current_user.id,
            start=from_,
            end=to,
            date_field=date_field,
            user_id=user_id,
            show_completed=show_completed,
            today=date.today(),
        )
    except RangeTooLongError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ScheduleListResponse(
        items=[
            ScheduleEventResponse(
                post_id=event.post_id,
                lawsuit_id=event.lawsuit_id,
                task_type_name=event.task_type_name,
                date=event.axis_date,
                scheduled_date=event.scheduled_date,
                scheduled_time=event.scheduled_time,
                end_date=event.end_date,
                end_time=event.end_time,
                deadline_date=event.deadline_date,
                all_day=event.all_day,
                location=event.location,
                status=event.status,
                is_urgent=event.is_urgent,
                is_important=event.is_important,
                assignee_names=event.assignee_names,
            )
            for event in events
        ]
    )


@router.get("/schedule/ical", response_model=ICalStatusResponse)
async def get_ical_status(
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
) -> ICalStatusResponse:
    """Estado atual do feed do usuário — o ICalSettingsCard precisa saber se já está
    ativo sem regenerar o token."""
    return ICalStatusResponse(
        enabled=current_user.ical_enabled,
        url=f"/ical/{current_user.ical_token}.ics" if current_user.ical_enabled else None,
    )


@router.post("/schedule/ical/enable", response_model=ICalEnableResponse)
async def enable_ical(
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> ICalEnableResponse:
    url = await ScheduleService(session).enable_ical(user_id=current_user.id)
    return ICalEnableResponse(enabled=True, url=url)


@router.post("/schedule/ical/regenerate", response_model=ICalEnableResponse)
async def regenerate_ical(
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> ICalEnableResponse:
    url = await ScheduleService(session).regenerate_ical(user_id=current_user.id)
    return ICalEnableResponse(enabled=True, url=url)


@ical_router.get("/ical/{token}.ics")
async def ical_feed(token: str, request: Request) -> Response:
    """Feed público por token (spec 037 §5 — fora de /api/v1). A URL é o segredo:
    o token resolve (tenant, usuário) via função SECURITY DEFINER e só então a
    sessão seta o tenant — o RLS continua valendo para as queries do feed.
    Sincronização unidirecional (regra 6): o feed é somente leitura por definição."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session, session.begin():
        resolved = await resolve_feed_token(session, token)
        if resolved is None:
            raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)
        tenant_id, user_id = resolved
        await set_tenant_context(session, tenant_id)
        user = await session.get(User, user_id)
        if user is None or not user.is_active:
            raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)
        account = await AccountRepository(session).get_current()
        timezone_name = account.timezone if account else "America/Sao_Paulo"
        events = await ScheduleService(session).feed_events(user_id=user_id, today=date.today())
        content = build_ical(
            events,
            timezone_name=timezone_name,
            calendar_name=f"Rito — {user.name}",
        )
    return Response(
        content=content,
        media_type="text/calendar",
        headers={"Content-Disposition": 'inline; filename="rito.ics"'},
    )
