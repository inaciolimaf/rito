"""Listagem global de atividades (spec 128) — a tela `/posts`.

Separado de `repository.py` pelo mesmo motivo da listagem de processos (027): aqui só vive
a query da tela, que é a mais exigente do módulo (visibilidade da tarefa privada dentro do
`WHERE`, responsáveis agregados sem N+1, keyset sobre coluna anulável).

Duas decisões estruturais que valem para o arquivo inteiro:

- **`EXISTS`, nunca `JOIN`, para o que atravessa `post_users`.** Uma tarefa com três
  responsáveis apareceria três vezes, e o `DISTINCT` que conserta a lista estragaria o
  `count(*) OVER ()` que traz o `total` — ele passaria a contar linha de junção.
- **Keyset sobre data anulável.** `(valor, id)` é comparado como TUPLA; `NULL` do lado
  esquerdo torna a comparação `NULL` e a linha sumiria da segunda página em diante. O
  `coalesce` com o extremo do calendário resolve ordenação e cursor de uma vez.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from sqlalchemy import ColumnElement, Row, Select, and_, func, literal, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.selectable import Subquery

from app.core.listing import (
    Column,
    Page,
    QuickViews,
    date_range,
    datetime_range,
    paginate_keyset,
)
from app.domain.lawsuits.models import Lawsuit
from app.domain.posts.models import Post, PostUser
from app.domain.posts.schemas import ActivityFiltersQuery
from app.domain.task_types.models import TaskType
from app.domain.users.models import User

Predicate = ColumnElement[bool]

# Regra 7: mesmo teto da listagem de contatos (019) e de processos (027).
EXPORT_ROW_LIMIT = 50_000

DateAxis = Literal["scheduled", "deadline", "created", "completed"]
SortField = Literal["scheduled_date", "deadline_date", "created_at"]
ActivityStatus = Literal["PENDENTE", "CONCLUIDA", "ATRASADA"]


def _pending_line() -> Predicate:
    """Existe responsável com a linha em aberto (spec 033, regra 1: conclusão é por
    responsável, e a tarefa só fecha quando todas as linhas fecham)."""
    return (
        select(PostUser.id)
        .where(PostUser.post_id == Post.id, PostUser.completed_at.is_(None))
        .exists()
    )


def _limit_date() -> ColumnElement[date]:
    """A data que define atraso: prazo fatal quando existe, senão o compromisso."""
    return func.coalesce(Post.deadline_date, Post.scheduled_date)


# Regra 5: as quatro visões rápidas. `pending` é o default — abrir Atividades é olhar o que
# falta fazer, não o histórico. `overdue` é o terceiro status colorido da agenda no
# levantamento (§4.2), e por isso é visão e não filtro separado.
ACTIVITY_VIEWS = QuickViews(
    default="pending",
    views={
        "all": lambda: None,
        "pending": _pending_line,
        "completed": lambda: ~_pending_line(),
        "overdue": lambda: and_(_pending_line(), _limit_date() < func.current_date()),
    },
)

_AXIS_COLUMNS: dict[str, InstrumentedAttribute[Any]] = {
    "scheduled": Post.scheduled_date,
    "deadline": Post.deadline_date,
    "created": Post.created_at,
}

_SORT_COLUMNS: dict[str, InstrumentedAttribute[Any]] = {
    "scheduled_date": Post.scheduled_date,
    "deadline_date": Post.deadline_date,
    "created_at": Post.created_at,
}

_PRIORITY_FLAGS: dict[str, InstrumentedAttribute[bool]] = {
    "important": Post.is_important,
    "urgent": Post.is_urgent,
}


@dataclass(frozen=True, slots=True)
class ActivityFilters:
    """Filtros da tela (spec 128 §6) — combinam com AND entre si.

    `column` não é filtro: escolhe SOBRE QUAL data o par `date_from`/`date_to` incide.
    Fica junto porque sem ele o par é ambíguo — mesma decisão do `by_deadline` do
    `TaskQuery` da busca de tarefas (083)."""

    view: str = ACTIVITY_VIEWS.default
    column: DateAxis = "scheduled"
    date_from: date | None = None
    date_to: date | None = None
    task_type_id: uuid.UUID | None = None
    lawsuit_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    sender: Literal["received", "sent"] | None = None
    priority: tuple[str, ...] = ()
    include_future: bool = False


@dataclass
class ActivityListRow:
    """Uma linha da tela. `sort_value` é o valor de ordenação JÁ coalescido — quem monta o
    próximo cursor precisa exatamente dele, e recalculá-lo fora daqui duplicaria a regra do
    sentinela. `Any` porque a coluna de ordenação muda de tipo com o `sort` (data ou
    timestamp), o mesmo motivo do `Any` no cursor de `core/listing.py`."""

    post: Post
    task_type_name: str
    process_number: str | None
    folder: str | None
    assignee_names: list[str]
    assignees_total: int
    pending_count: int
    sort_value: Any


def filters_from_query(payload: ActivityFiltersQuery) -> ActivityFilters:
    """Traduz o modelo de query string para os filtros do domínio. `priority` chega em
    CSV (`important,urgent`) e vira tupla; visão desconhecida cai no default."""
    priority = tuple(value for value in (payload.priority or "").split(",") if value)
    return ActivityFilters(
        view=ACTIVITY_VIEWS.resolve(payload.view),
        column=payload.column,
        date_from=payload.date_from,
        date_to=payload.date_to,
        task_type_id=payload.task_type_id,
        lawsuit_id=payload.lawsuit_id,
        assignee_id=payload.assignee_id,
        sender=payload.sender,
        priority=priority,
        include_future=payload.include_future,
    )


def visible_to(viewer_id: uuid.UUID) -> Predicate:
    """Regra 8 da spec 033 escrita como `WHERE`: tarefa privada só existe para o criador e
    os responsáveis — nem o GESTOR a vê.

    Estar no `WHERE` (e não num filtro sobre o resultado) é o que faz `total`,
    `next_cursor` e export contarem a mesma coisa que a página mostra. Filtrar depois
    devolveria páginas de 17 linhas e um total que não fecha."""
    return or_(
        Post.is_private.is_(False),
        Post.created_by == viewer_id,
        select(PostUser.id)
        .where(PostUser.post_id == Post.id, PostUser.user_id == viewer_id)
        .exists(),
    )


def _future_hidden(today: date) -> Predicate:
    """Regra 7 da 033: tarefa futura fica oculta até a data do compromisso."""
    return or_(
        Post.is_future.is_(False),
        and_(Post.scheduled_date.is_not(None), Post.scheduled_date <= today),
    )


def _period_conditions(filters: ActivityFilters) -> list[Predicate]:
    """Regra 4: o período incide sobre o eixo de `column`.

    Conclusão é o único eixo que não é coluna de `posts` — é data da LINHA do responsável
    (033, regra 1) —, então vira `EXISTS` em vez de comparação direta."""
    if filters.column == "completed":
        janela = datetime_range(PostUser.completed_at, filters.date_from, filters.date_to)
        if not janela:
            return []
        return [select(PostUser.id).where(PostUser.post_id == Post.id, *janela).exists()]
    coluna = _AXIS_COLUMNS[filters.column]
    intervalo = datetime_range if filters.column == "created" else date_range
    return intervalo(coluna, filters.date_from, filters.date_to)


def _people_conditions(filters: ActivityFilters, viewer_id: uuid.UUID) -> list[Predicate]:
    """Responsável e remetente. `sender` é o par "que eu recebi / que eu enviei" do
    levantamento: recebi = sou responsável; enviei = sou o criador."""
    condicoes: list[Predicate] = []
    if filters.assignee_id is not None:
        condicoes.append(_assigned_to(filters.assignee_id))
    if filters.sender == "received":
        condicoes.append(_assigned_to(viewer_id))
    if filters.sender == "sent":
        condicoes.append(Post.created_by == viewer_id)
    return condicoes


def _assigned_to(user_id: uuid.UUID) -> Predicate:
    return (
        select(PostUser.id).where(PostUser.post_id == Post.id, PostUser.user_id == user_id).exists()
    )


def _direct_conditions(filters: ActivityFilters) -> list[Predicate]:
    """Os que são só «coluna = valor» na própria tarefa, mais a prioridade — que é OR
    entre as flags escolhidas (regra 10 da 033: importante e urgente são independentes e
    combináveis, então marcar as duas é «uma OU a outra», não «as duas»)."""
    condicoes: list[Predicate] = []
    if filters.task_type_id is not None:
        condicoes.append(Post.task_type_id == filters.task_type_id)
    if filters.lawsuit_id is not None:
        condicoes.append(Post.lawsuit_id == filters.lawsuit_id)
    flags = [coluna for nome, coluna in _PRIORITY_FLAGS.items() if nome in filters.priority]
    if flags:
        condicoes.append(or_(*(coluna.is_(True) for coluna in flags)))
    return condicoes


def build_conditions(
    filters: ActivityFilters, *, viewer_id: uuid.UUID, today: date
) -> list[Predicate]:
    """Todas as condições da tela, na ordem em que se lê a regra: quem pode ver, qual
    visão, futuras, período, filtros diretos, pessoas."""
    condicoes: list[Predicate] = [visible_to(viewer_id)]
    visao = ACTIVITY_VIEWS.predicate(filters.view)
    if visao is not None:
        condicoes.append(visao)
    if not filters.include_future:
        condicoes.append(_future_hidden(today))
    condicoes += _period_conditions(filters)
    condicoes += _direct_conditions(filters)
    condicoes += _people_conditions(filters, viewer_id)
    return condicoes


def sort_column_for(sort: str, *, descending: bool) -> Column:
    """Regra 6: data nula ordena no fim, nas duas direções — e continua comparável pelo
    cursor. Ver o cabeçalho do módulo para o porquê do `coalesce`."""
    coluna = _SORT_COLUMNS[sort]
    if sort == "created_at":
        return coluna  # `created_at` é NOT NULL: sentinela seria ruído.
    return func.coalesce(coluna, literal(date.min if descending else date.max))


def decode_sort_value(sort: str, raw: str) -> date | datetime:
    """O cursor viaja como texto; a comparação `(valor, id)` precisa do tipo certo, senão
    o Postgres recusa `date < varchar` — e só na SEGUNDA página, que é o pior lugar para
    descobrir (mesma lição da spec 095)."""
    return datetime.fromisoformat(raw) if sort == "created_at" else date.fromisoformat(raw)


def status_of(row: ActivityListRow, today: date) -> ActivityStatus:
    """Regra 10: status é derivado, nunca persistido. Concluída = TODAS as linhas
    concluídas (033, regra 3); atrasada = pendente com a data limite no passado."""
    if row.assignees_total > 0 and row.pending_count == 0:
        return "CONCLUIDA"
    limite = row.post.deadline_date or row.post.scheduled_date
    return "ATRASADA" if limite is not None and limite < today else "PENDENTE"


def _to_row(row: Row[Any], sort_values: dict[uuid.UUID, Any]) -> ActivityListRow:
    """Lida por POSIÇÃO — a ordem é a do `_labels_query`. As coalescências existem porque
    o `OUTER JOIN` devolve `NULL` para uma tarefa sem responsável, e a tela precisa de
    lista vazia e zero."""
    post = row[0]
    return ActivityListRow(
        post=post,
        task_type_name=row[1],
        process_number=row[2],
        folder=row[3],
        assignee_names=list(row[4] or []),
        assignees_total=row[5] or 0,
        pending_count=row[6] or 0,
        sort_value=sort_values[post.id],
    )


class ActivityListingRepository:
    """Query da listagem de atividades — não herda `BaseRepository` (não é CRUD)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _assignees_subquery(self, post_ids: Sequence[uuid.UUID]) -> Subquery:
        """Responsáveis agregados por tarefa, restritos às linhas da página. Nomes em
        ordem alfabética: o `json_agg` do Postgres agrega em scan order, então a ordem vem
        de uma subquery ordenada antes (mesmo padrão das partes na listagem de 027)."""
        ordenados = (
            select(
                PostUser.post_id.label("post_id"),
                User.name.label("name"),
                PostUser.completed_at.label("completed_at"),
            )
            .join(User, User.id == PostUser.user_id)
            .where(PostUser.post_id.in_(post_ids))
            .order_by(PostUser.post_id, User.name)
            .subquery()
        )
        return (
            select(
                ordenados.c.post_id,
                func.json_agg(ordenados.c.name, type_=JSONB).label("names"),
                func.count().label("total"),
                func.count().filter(ordenados.c.completed_at.is_(None)).label("pending"),
            )
            .group_by(ordenados.c.post_id)
            .subquery()
        )

    def _labels_query(
        self, ids: list[uuid.UUID], sort_column: Column, *, descending: bool
    ) -> Select[Any]:
        """A segunda metade do JOIN DIFERIDO: os rótulos das linhas já escolhidas.

        A ordenação é REPETIDA aqui porque `IN` não preserva ordem nenhuma — sem isso a
        página sairia embaralhada em relação ao cursor que a produziu."""
        responsaveis = self._assignees_subquery(ids)
        ordem = sort_column.desc() if descending else sort_column.asc()
        desempate = Post.id.desc() if descending else Post.id.asc()
        return (
            select(
                Post,
                TaskType.name,
                Lawsuit.process_number,
                Lawsuit.folder,
                responsaveis.c.names,
                responsaveis.c.total,
                responsaveis.c.pending,
            )
            .join(TaskType, TaskType.id == Post.task_type_id)
            .join(Lawsuit, Lawsuit.id == Post.lawsuit_id)
            .outerjoin(responsaveis, responsaveis.c.post_id == Post.id)
            .where(Post.id.in_(ids))
            .order_by(ordem, desempate)
        )

    async def _page_ids(
        self, conditions: list[Predicate], *, sort_column: Column, page: Page
    ) -> tuple[list[Row[Any]], int]:
        """Ids da página e total do filtro numa query só: o total sai por função de janela
        sobre o MESMO conjunto de linhas, e não por um `count(*)` que percorreria a faixa
        de novo (spec 098, regra 1)."""
        stmt = select(
            Post.id, sort_column.label("sort_value"), func.count().over().label("total")
        ).select_from(Post)
        for condition in conditions:
            stmt = stmt.where(condition)
        stmt = paginate_keyset(
            stmt,
            sort_column=sort_column,
            id_column=Post.id,
            descending=page.descending,
            cursor=page.cursor,
            limit=page.limit,
        )
        linhas = (await self.session.execute(stmt)).all()
        # Página vazia é filtro sem resultado — a janela não existe e zero é o total.
        return list(linhas), (int(linhas[0].total) if linhas else 0)

    async def list_filtered(
        self, *, conditions: list[Predicate], page: Page
    ) -> tuple[list[ActivityListRow], int]:
        """JOIN DIFERIDO em 2 statements (regra 9): a página sai só de `posts`, e os três
        rótulos caem sobre as linhas escolhidas."""
        sort_column = sort_column_for(page.sort, descending=page.descending)
        escolhidas, total = await self._page_ids(conditions, sort_column=sort_column, page=page)
        if not escolhidas:
            return [], total
        ids = [linha.id for linha in escolhidas]
        valores = {linha.id: linha.sort_value for linha in escolhidas}
        query = self._labels_query(ids, sort_column, descending=page.descending)
        rotulos = (await self.session.execute(query)).all()
        return [_to_row(linha, valores) for linha in rotulos], total
