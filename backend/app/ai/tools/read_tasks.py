"""Ferramentas de leitura de tarefas e agenda (spec 083).

Regra 3 mora aqui: tarefa privada de terceiro não aparece. A ferramenta não reimplementa
essa checagem — ela usa o `ScheduleService`, que já filtra por criador/responsável
(spec 037), e o `InboxService`, cuja consulta é por definição a caixa do próprio
usuário. Reimplementar a regra criaria uma segunda versão dela para divergir.
"""

import uuid
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, Field

from app.ai.tools.base import MAX_ROWS, ToolContext, tool, truncate_rows
from app.domain.inbox.service import InboxService
from app.domain.posts.service import PostService

_DEFAULT_WINDOW_DAYS = 30


class SearchTasksInput(BaseModel):
    date_from: date | None = Field(default=None, description="Padrão: hoje.")
    date_to: date | None = Field(default=None, description="Padrão: 30 dias à frente.")
    responsible_id: uuid.UUID | None = Field(
        default=None, description="Omitido = tarefas de todo o escritório."
    )
    by_deadline: bool = Field(
        default=False, description="Filtrar pelo prazo fatal em vez da data do compromisso."
    )
    include_completed: bool = False
    limit: int = Field(default=20, ge=1, le=MAX_ROWS)


class GetInboxInput(BaseModel):
    section: str = Field(
        default="deadline",
        description="deadline | publications | unread | urgent | important | others",
    )
    limit: int = Field(default=20, ge=1, le=MAX_ROWS)


@tool(
    name="search_tasks",
    description=(
        "Tarefas e compromissos por período, responsável e situação. "
        "Use para 'o que vence esta semana', 'tarefas do fulano', 'prazos de amanhã'."
    ),
)
async def search_tasks(ctx: ToolContext, params: SearchTasksInput) -> dict[str, Any]:
    today = date.today()
    start = params.date_from or today
    end = params.date_to or (start + timedelta(days=_DEFAULT_WINDOW_DAYS))
    service = PostService(session=ctx.session, tenant_id=ctx.tenant_id)
    details = await service.search(
        viewer_id=ctx.user.id,
        date_from=start,
        date_to=end,
        by_deadline=params.by_deadline,
        assignee_id=params.responsible_id,
        only_open=not params.include_completed,
        limit=min(params.limit, MAX_ROWS) + 1,
    )
    items, truncated = truncate_rows(details, params.limit)
    return {
        "period": {"from": start.isoformat(), "to": end.isoformat()},
        "items": [
            {
                "post_id": str(detail.post.id),
                "lawsuit_id": str(detail.post.lawsuit_id),
                "task_type": detail.task_type_name,
                "scheduled_date": (
                    detail.post.scheduled_date.isoformat() if detail.post.scheduled_date else None
                ),
                "deadline_date": (
                    detail.post.deadline_date.isoformat() if detail.post.deadline_date else None
                ),
                "completed": bool(detail.assignees)
                and all(item.line.completed_at is not None for item in detail.assignees),
                "is_urgent": detail.post.is_urgent,
                "is_important": detail.post.is_important,
                "assignees": [item.user.name for item in detail.assignees],
            }
            for detail in items
        ],
        "total": len(details),
        "truncated": truncated,
    }


@tool(
    name="get_inbox",
    description=(
        "Caixa de entrada do próprio usuário, por seção. "
        "Use para 'o que eu tenho para hoje' e 'meus prazos'."
    ),
)
async def get_inbox(ctx: ToolContext, params: GetInboxInput) -> dict[str, Any]:
    service = InboxService(session=ctx.session, tenant_id=ctx.tenant_id)
    counts = await service.counts(ctx.user)
    rows, has_more = await service.list_section(
        ctx.user,
        section=params.section,
        cursor=None,
        limit=min(params.limit, MAX_ROWS),
    )
    return {
        "section": params.section,
        "counts": counts,
        "items": [
            {
                "post_id": str(row.post_id),
                "lawsuit_id": str(row.lawsuit_id),
                "task_type": row.task_type_name,
                "scheduled_date": row.scheduled_date.isoformat() if row.scheduled_date else None,
                "deadline_date": row.deadline_date.isoformat() if row.deadline_date else None,
                "is_urgent": row.is_urgent,
                "is_important": row.is_important,
                "parties": row.parties,
            }
            for row in rows
        ],
        "truncated": has_more,
    }
