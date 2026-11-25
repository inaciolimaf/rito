"""Export xlsx/pdf da listagem de processos (spec 027, regra 10) — colunas do domínio
sobre o `TableExport` genérico (spec 030)."""

from datetime import datetime

from app.core.clock import Clock
from app.core.export import ExportColumn, TableExport
from app.domain.lawsuits.listing import LawsuitListRow


def _parties(row: LawsuitListRow) -> str:
    # Regra 12: as 2 primeiras partes + contador do restante.
    names = [str(party["name"]) for party in row.parties[:2]]
    if row.parties_total > 2:
        names.append(f"+{row.parties_total - 2}")
    return ", ".join(names)


def _office_day_br(instant: datetime, clock: Clock) -> str:
    """`DD/MM/AAAA` do dia em que `instant` caiu no fuso do escritório (spec 136).

    Gêmea de `customers/export.py::_office_day_br`, e de propósito duplicada por
    enquanto: são dois usos, e a regra dos 3 usos do `CLAUDE.md` §6 dispara no terceiro —
    quando disparar, o lugar dela é `app/core/export.py`, junto do `TableExport` que já é
    o dono da mecânica do arquivo. Ver a §9 da spec 136.
    """
    return instant.astimezone(clock.timezone).strftime("%d/%m/%Y")


def _export(clock: Clock) -> TableExport[LawsuitListRow]:
    return TableExport[LawsuitListRow](
        sheet_title="Processos",
        columns=[
            ExportColumn("Partes", _parties),
            ExportColumn("Tipo de ação", lambda row: row.lawsuit_type_name),
            ExportColumn("Número do processo", lambda row: row.lawsuit.process_number or ""),
            ExportColumn(
                "Data de cadastro", lambda row: _office_day_br(row.lawsuit.created_at, clock)
            ),
            ExportColumn("Último andamento", lambda row: row.last_movement_title or ""),
        ],
    )


def build_xlsx(rows: list[LawsuitListRow], clock: Clock | None = None) -> bytes:
    return _export(clock or Clock()).xlsx(rows)


def build_pdf(rows: list[LawsuitListRow], clock: Clock | None = None) -> bytes:
    return _export(clock or Clock()).pdf(rows)
