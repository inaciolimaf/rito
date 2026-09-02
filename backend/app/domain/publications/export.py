"""Export xlsx/pdf da listagem de intimações (spec 048, regra 9) — colunas do
domínio sobre o `TableExport` genérico (spec 030)."""

from app.core.export import ExportColumn, TableExport
from app.domain.publications.schemas import PublicationListRow


def _parties(row: PublicationListRow) -> str:
    names = row.parties[:2]
    if len(row.parties) > 2:
        names = [*names, f"+{len(row.parties) - 2}"]
    return ", ".join(names)


def _status(row: PublicationListRow) -> str:
    if not row.publication.is_active:
        return f"Cancelada — {row.publication.cancellation_reason or 'sem motivo informado'}"
    return "Vinculada" if row.publication.lawsuit_id else "Não vinculada"


_EXPORT = TableExport[PublicationListRow](
    sheet_title="Intimações",
    columns=[
        ExportColumn(
            "Data de disponibilização",
            lambda row: row.publication.availability_date.strftime("%d/%m/%Y"),
        ),
        ExportColumn("Tribunal", lambda row: row.publication.court_code),
        ExportColumn("Órgão", lambda row: row.publication.organ_name or ""),
        ExportColumn("Processo", lambda row: row.publication.process_number or ""),
        ExportColumn("Partes", _parties),
        ExportColumn("Responsável", lambda row: row.routed_to_name or ""),
        ExportColumn("Status", _status),
    ],
)


def build_xlsx(rows: list[PublicationListRow]) -> bytes:
    return _EXPORT.xlsx(rows)


def build_pdf(rows: list[PublicationListRow]) -> bytes:
    return _EXPORT.pdf(rows)
