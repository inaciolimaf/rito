"""Export xlsx/pdf da listagem de processos (spec 027, regra 10) — colunas do domínio
sobre o `TableExport` genérico (spec 030)."""

from app.core.export import ExportColumn, TableExport
from app.domain.lawsuits.listing import LawsuitListRow


def _parties(row: LawsuitListRow) -> str:
    # Regra 12: as 2 primeiras partes + contador do restante.
    names = [str(party["name"]) for party in row.parties[:2]]
    if row.parties_total > 2:
        names.append(f"+{row.parties_total - 2}")
    return ", ".join(names)


_EXPORT = TableExport[LawsuitListRow](
    sheet_title="Processos",
    columns=[
        ExportColumn("Partes", _parties),
        ExportColumn("Tipo de ação", lambda row: row.lawsuit_type_name),
        ExportColumn("Número do processo", lambda row: row.lawsuit.process_number or ""),
        ExportColumn("Data de cadastro", lambda row: row.lawsuit.created_at.strftime("%d/%m/%Y")),
        ExportColumn("Último andamento", lambda row: row.last_movement_title or ""),
    ],
)


def build_xlsx(rows: list[LawsuitListRow]) -> bytes:
    return _EXPORT.xlsx(rows)


def build_pdf(rows: list[LawsuitListRow]) -> bytes:
    return _EXPORT.pdf(rows)
