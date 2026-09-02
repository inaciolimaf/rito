"""Orquestração dos 9 relatórios tabulares (spec 072) — cada relatório é definido
por metadados (regra 1): a rota genérica do router só sabe despachar por `report_key`,
a query específica vive no repositório, a montagem da linha tipada vive aqui."""

import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.export import ExportColumn, TableExport
from app.core.repository import decode_cursor, encode_cursor
from app.domain.account.models import DEFAULT_TIMEZONE
from app.domain.account.repository import AccountRepository
from app.domain.lawsuits.models import LawsuitOutcome
from app.domain.reports.schemas import (
    AccessLogRow,
    ContraryPartyRow,
    DelayedTaskRowItem,
    HearingRow,
    LawsuitOutcomeRow,
    NewCustomerRow,
    NewLawsuitRow,
    ProductivityRow,
    ReportKey,
    ReportListResponse,
    ReportRow,
)
from app.domain.reports.tabular_repository import TabularReportRepository

_EXPORT_ROW_CAP = 50_000

# Regra 5: relatório desligado enquanto `accounts.track_access_logs` for False —
# desligado é o padrão (spec 073, regra 1).
_ACCESS_LOGS_DISABLED_REASON = "Rastreamento de acesso desligado."


@dataclass(frozen=True)
class ReportFilters:
    from_: date | None = None
    to: date | None = None
    user_id: uuid.UUID | None = None
    action_group_id: uuid.UUID | None = None


def _decode_date_cursor(cursor: str | None) -> tuple[date, uuid.UUID] | None:
    if cursor is None:
        return None
    raw_value, id_ = decode_cursor(cursor)
    return date.fromisoformat(raw_value), id_


def _decode_datetime_cursor(cursor: str | None) -> tuple[datetime, uuid.UUID] | None:
    if cursor is None:
        return None
    raw_value, id_ = decode_cursor(cursor)
    return datetime.fromisoformat(raw_value), id_


def _decode_int_cursor(cursor: str | None) -> tuple[int, uuid.UUID] | None:
    if cursor is None:
        return None
    raw_value, id_ = decode_cursor(cursor)
    return int(raw_value), id_


def _decode_str_cursor(cursor: str | None) -> tuple[str, uuid.UUID] | None:
    if cursor is None:
        return None
    return decode_cursor(cursor)


# Assinatura comum dos relatórios da tabela de despacho. `report_key` chega em todos,
# mesmo nos que não olham para ela: é o preço de ter uma tabela uniforme, e a alternativa
# — uma assinatura por relatório — tornaria o despacho intipável.
_Relatorio = Callable[..., Awaitable["ReportListResponse"]]


class TabularReportService:
    def __init__(
        self, session: AsyncSession, tenant_id: uuid.UUID, timezone: str = DEFAULT_TIMEZONE
    ) -> None:
        self.repo = TabularReportRepository(session, timezone)
        self.accounts = AccountRepository(session)
        self.tenant_id = tenant_id

    async def fetch(
        self,
        report_key: ReportKey,
        filters: ReportFilters,
        *,
        cursor: str | None,
        limit: int,
        today: date,
    ) -> ReportListResponse:
        """Despacha para o relatório pedido (spec 106).

        Era uma cadeia de oito `if report_key == ...`, cada um com ~25 linhas de montagem
        de linha. A tabela abaixo é a mesma decisão escrita uma vez: relatório novo é uma
        entrada aqui mais um método, e o `ReportKey` continua sendo a fonte das chaves —
        chave que não existe no enum não compila.
        """
        relatorio = self._RELATORIOS[report_key]
        resposta: ReportListResponse = await relatorio(
            self, report_key, filters, cursor=cursor, limit=limit, today=today
        )
        return resposta

    async def _relatorio_productivity(
        self,
        report_key: ReportKey,
        filters: ReportFilters,
        *,
        cursor: str | None,
        limit: int,
        today: date,
    ) -> ReportListResponse:
        rows, total, points_total = await self.repo.productivity(
            user_id=filters.user_id,
            action_group_id=filters.action_group_id,
            from_=filters.from_,
            to=filters.to,
            cursor=_decode_date_cursor(cursor),
            limit=limit,
        )
        items: list[ReportRow] = [
            ProductivityRow(
                post_id=r[0],
                responsible_name=r[1],
                customer_name=r[2],
                task_type_name=r[3],
                points=r[4] or 0,
                scheduled_date=r[5],
                completed_at=r[6],
            )
            for r in rows
        ]
        next_cursor = _next_cursor(rows, items, limit, lambda r: r.scheduled_date)
        return ReportListResponse(
            items=items, next_cursor=next_cursor, total=total, points_total=points_total
        )

    async def _relatorio_delayed_tasks(
        self,
        report_key: ReportKey,
        filters: ReportFilters,
        *,
        cursor: str | None,
        limit: int,
        today: date,
    ) -> ReportListResponse:
        rows, total, points_total = await self.repo.delayed_tasks(
            user_id=filters.user_id,
            action_group_id=filters.action_group_id,
            from_=filters.from_,
            to=filters.to,
            cursor=_decode_int_cursor(cursor),
            limit=limit,
        )
        items = [
            DelayedTaskRowItem(
                post_id=r[0],
                responsible_name=r[1],
                customer_name=r[2],
                task_type_name=r[3],
                points=r[4] or 0,
                scheduled_date=r[5],
                delay_days=int(r[6]),
            )
            for r in rows
        ]
        next_cursor = _next_cursor(rows, items, limit, lambda r: r.delay_days)
        return ReportListResponse(
            items=items, next_cursor=next_cursor, total=total, points_total=points_total
        )

    async def _relatorio_access_logs(
        self,
        report_key: ReportKey,
        filters: ReportFilters,
        *,
        cursor: str | None,
        limit: int,
        today: date,
    ) -> ReportListResponse:
        account = await self.accounts.get_current()
        if account is None or not account.track_access_logs:
            # Regra 5: desligado é o padrão (spec 073, regra 1) — estado vazio
            # explicativo, não lista vazia crua.
            return ReportListResponse(
                items=[],
                next_cursor=None,
                total=0,
                disabled_reason=_ACCESS_LOGS_DISABLED_REASON,
            )
        rows, total = await self.repo.access_logs_from_timesheet(
            cursor=_decode_date_cursor(cursor), limit=limit
        )
        items = [
            AccessLogRow(
                user_id=r[0],
                user_name=r[1],
                day=r[2],
                ip_address=str(r[3]) if r[3] else None,
                first_login=r[4],
                last_login=r[5],
            )
            for r in rows
        ]
        next_cursor = _next_cursor(rows, items, limit, lambda r: r.day)
        return ReportListResponse(items=items, next_cursor=next_cursor, total=total)

    async def _relatorio_new_customers(
        self,
        report_key: ReportKey,
        filters: ReportFilters,
        *,
        cursor: str | None,
        limit: int,
        today: date,
    ) -> ReportListResponse:
        rows, total = await self.repo.new_customers(
            from_=filters.from_,
            to=filters.to,
            cursor=_decode_datetime_cursor(cursor),
            limit=limit,
        )
        items = [
            NewCustomerRow(
                customer_id=r[0],
                name=r[1],
                contact=r[2],
                city_state=r[3],
                origin_name=r[4],
                created_at=r[5],
            )
            for r in rows
        ]
        next_cursor = _next_cursor(rows, items, limit, lambda r: r.created_at)
        return ReportListResponse(items=items, next_cursor=next_cursor, total=total)

    async def _relatorio_new_lawsuits(
        self,
        report_key: ReportKey,
        filters: ReportFilters,
        *,
        cursor: str | None,
        limit: int,
        today: date,
    ) -> ReportListResponse:
        rows, total = await self.repo.new_lawsuits(
            user_id=filters.user_id,
            action_group_id=filters.action_group_id,
            from_=filters.from_,
            to=filters.to,
            cursor=_decode_datetime_cursor(cursor),
            limit=limit,
        )
        items = [
            NewLawsuitRow(
                lawsuit_id=r[0],
                parties=r[1],
                lawsuit_type_name=r[2],
                process_number=r[3],
                responsible_name=r[4],
                created_at=r[5],
            )
            for r in rows
        ]
        next_cursor = _next_cursor(rows, items, limit, lambda r: r.created_at)
        return ReportListResponse(items=items, next_cursor=next_cursor, total=total)

    async def _relatorio_won_lost(
        self,
        report_key: ReportKey,
        filters: ReportFilters,
        *,
        cursor: str | None,
        limit: int,
        today: date,
    ) -> ReportListResponse:
        outcome = LawsuitOutcome.GANHO if report_key == "won_lawsuits" else LawsuitOutcome.PERDIDO
        rows, total = await self.repo.lawsuits_by_outcome(
            outcome=outcome,
            user_id=filters.user_id,
            action_group_id=filters.action_group_id,
            from_=filters.from_,
            to=filters.to,
            cursor=_decode_date_cursor(cursor),
            limit=limit,
        )
        items = [
            LawsuitOutcomeRow(
                lawsuit_id=r[0],
                parties=r[1],
                lawsuit_type_name=r[2],
                process_number=r[3],
                fees_value=r[4],
                closure_date=r[5],
                total_days=int(r[6]),
            )
            for r in rows
        ]
        next_cursor = _next_cursor(rows, items, limit, lambda r: r.closure_date)
        return ReportListResponse(items=items, next_cursor=next_cursor, total=total)

    async def _relatorio_hearings(
        self,
        report_key: ReportKey,
        filters: ReportFilters,
        *,
        cursor: str | None,
        limit: int,
        today: date,
    ) -> ReportListResponse:
        rows, total = await self.repo.hearings(
            cursor=_decode_date_cursor(cursor), limit=limit, today=today
        )
        items = [
            HearingRow(
                post_id=r[0],
                scheduled_date=r[1],
                scheduled_time=r[2],
                task_type_name=r[3],
                process_number=r[4],
                parties=r[5],
                location=r[6],
                responsible_name=r[7],
            )
            for r in rows
        ]
        next_cursor = _next_cursor(rows, items, limit, lambda r: r.scheduled_date)
        return ReportListResponse(items=items, next_cursor=next_cursor, total=total)

    async def _relatorio_contrary_parties(
        self,
        report_key: ReportKey,
        filters: ReportFilters,
        *,
        cursor: str | None,
        limit: int,
        today: date,
    ) -> ReportListResponse:
        rows, total = await self.repo.contrary_parties(
            cursor=_decode_str_cursor(cursor), limit=limit
        )
        items = [
            ContraryPartyRow(
                customer_id=r[0],
                name=r[1],
                identification=r[2],
                city=r[3],
                lawsuit_count=int(r[4]),
            )
            for r in rows
        ]
        next_cursor = _next_cursor(rows, items, limit, lambda r: r.name)
        return ReportListResponse(items=items, next_cursor=next_cursor, total=total)

    # Tabela de despacho — declarada depois dos métodos porque referencia todos eles.
    _RELATORIOS: ClassVar[dict[str, _Relatorio]] = {
        "productivity": _relatorio_productivity,
        "delayed_tasks": _relatorio_delayed_tasks,
        "access_logs": _relatorio_access_logs,
        "new_customers": _relatorio_new_customers,
        "new_lawsuits": _relatorio_new_lawsuits,
        "won_lawsuits": _relatorio_won_lost,
        "lost_lawsuits": _relatorio_won_lost,
        "hearings": _relatorio_hearings,
        "contrary_parties": _relatorio_contrary_parties,
    }

    async def export(
        self,
        report_key: ReportKey,
        filters: ReportFilters,
        *,
        format_: Literal["xlsx", "pdf"],
        today: date,
    ) -> bytes:
        # Regra 10: respeita os filtros ativos; teto de 50.000 linhas.
        result = await self.fetch(
            report_key, filters, cursor=None, limit=_EXPORT_ROW_CAP, today=today
        )
        columns = _EXPORT_COLUMNS[report_key]
        export = TableExport(sheet_title=report_key, columns=columns)
        return export.xlsx(result.items) if format_ == "xlsx" else export.pdf(result.items)


def _next_cursor(
    rows: Sequence[Any],
    items: Sequence[ReportRow],
    limit: int,
    sort_value: Callable[[Any], date | datetime | str | int],
) -> str | None:
    if len(items) < limit or not items:
        return None
    last = items[-1]
    value = sort_value(last)
    raw = value.isoformat() if isinstance(value, date | datetime) else str(value)
    return encode_cursor(raw, _row_id(last))


def _row_id(item: ReportRow) -> uuid.UUID:
    for attr in ("post_id", "customer_id", "lawsuit_id", "user_id"):
        value = getattr(item, attr, None)
        if isinstance(value, uuid.UUID):
            return value
    raise AssertionError("linha de relatório sem identificador")


def _str_or_empty(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return str(value)


_EXPORT_COLUMNS: dict[ReportKey, list[ExportColumn[Any]]] = {
    "productivity": [
        ExportColumn("Responsável", lambda r: _str_or_empty(r.responsible_name)),
        ExportColumn("Cliente", lambda r: _str_or_empty(r.customer_name)),
        ExportColumn("Tarefa", lambda r: _str_or_empty(r.task_type_name)),
        ExportColumn("Pontuação", lambda r: _str_or_empty(r.points)),
        ExportColumn("Data compromisso", lambda r: _str_or_empty(r.scheduled_date)),
        ExportColumn("Conclusão", lambda r: _str_or_empty(r.completed_at)),
    ],
    "delayed_tasks": [
        ExportColumn("Responsável", lambda r: _str_or_empty(r.responsible_name)),
        ExportColumn("Cliente", lambda r: _str_or_empty(r.customer_name)),
        ExportColumn("Tarefa", lambda r: _str_or_empty(r.task_type_name)),
        ExportColumn("Pontuação", lambda r: _str_or_empty(r.points)),
        ExportColumn("Data compromisso", lambda r: _str_or_empty(r.scheduled_date)),
        ExportColumn("Atraso (dias)", lambda r: _str_or_empty(r.delay_days)),
    ],
    "access_logs": [
        ExportColumn("Colaborador", lambda r: _str_or_empty(r.user_name)),
        ExportColumn("Data", lambda r: _str_or_empty(r.day)),
        ExportColumn("IP", lambda r: _str_or_empty(r.ip_address)),
        ExportColumn("Primeiro login", lambda r: _str_or_empty(r.first_login)),
        ExportColumn("Último login", lambda r: _str_or_empty(r.last_login)),
    ],
    "new_customers": [
        ExportColumn("Nome", lambda r: _str_or_empty(r.name)),
        ExportColumn("Contato", lambda r: _str_or_empty(r.contact)),
        ExportColumn("Cidade/UF", lambda r: _str_or_empty(r.city_state)),
        ExportColumn("Origem", lambda r: _str_or_empty(r.origin_name)),
        ExportColumn("Data", lambda r: _str_or_empty(r.created_at)),
    ],
    "new_lawsuits": [
        ExportColumn("Partes", lambda r: _str_or_empty(r.parties)),
        ExportColumn("Tipo de ação", lambda r: _str_or_empty(r.lawsuit_type_name)),
        ExportColumn("Número", lambda r: _str_or_empty(r.process_number)),
        ExportColumn("Responsável", lambda r: _str_or_empty(r.responsible_name)),
        ExportColumn("Data", lambda r: _str_or_empty(r.created_at)),
    ],
    "won_lawsuits": [
        ExportColumn("Partes", lambda r: _str_or_empty(r.parties)),
        ExportColumn("Tipo", lambda r: _str_or_empty(r.lawsuit_type_name)),
        ExportColumn("Número", lambda r: _str_or_empty(r.process_number)),
        ExportColumn("Honorários", lambda r: _str_or_empty(r.fees_value)),
        ExportColumn("Fechamento", lambda r: _str_or_empty(r.closure_date)),
        ExportColumn("Tempo total (dias)", lambda r: _str_or_empty(r.total_days)),
    ],
    "lost_lawsuits": [
        ExportColumn("Partes", lambda r: _str_or_empty(r.parties)),
        ExportColumn("Tipo", lambda r: _str_or_empty(r.lawsuit_type_name)),
        ExportColumn("Número", lambda r: _str_or_empty(r.process_number)),
        ExportColumn("Honorários", lambda r: _str_or_empty(r.fees_value)),
        ExportColumn("Fechamento", lambda r: _str_or_empty(r.closure_date)),
        ExportColumn("Tempo total (dias)", lambda r: _str_or_empty(r.total_days)),
    ],
    "hearings": [
        ExportColumn("Data", lambda r: _str_or_empty(r.scheduled_date)),
        ExportColumn("Hora", lambda r: _str_or_empty(r.scheduled_time)),
        ExportColumn("Tipo", lambda r: _str_or_empty(r.task_type_name)),
        ExportColumn("Processo", lambda r: _str_or_empty(r.process_number)),
        ExportColumn("Partes", lambda r: _str_or_empty(r.parties)),
        ExportColumn("Local", lambda r: _str_or_empty(r.location)),
        ExportColumn("Advogado", lambda r: _str_or_empty(r.responsible_name)),
    ],
    "contrary_parties": [
        ExportColumn("Nome", lambda r: _str_or_empty(r.name)),
        ExportColumn("Documento", lambda r: _str_or_empty(r.identification)),
        ExportColumn("Cidade", lambda r: _str_or_empty(r.city)),
        ExportColumn("Nº de processos", lambda r: _str_or_empty(r.lawsuit_count)),
    ],
}
