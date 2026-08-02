"""Export xlsx/pdf da listagem de processos (spec 027, regra 10) — mesmo padrão de
`app.domain.customers.export`."""

from io import BytesIO

from fpdf import FPDF
from openpyxl import Workbook

from app.domain.lawsuits.listing import LawsuitListRow

_COLUMNS = ("Partes", "Tipo de ação", "Número do processo", "Data de cadastro", "Último andamento")


def _row_for(row: LawsuitListRow) -> tuple[str, str, str, str, str]:
    # Regra 12: as 2 primeiras partes + contador do restante.
    names = [str(party["name"]) for party in row.parties[:2]]
    if row.parties_total > 2:
        names.append(f"+{row.parties_total - 2}")
    return (
        ", ".join(names),
        row.lawsuit_type_name,
        row.lawsuit.process_number or "",
        row.lawsuit.created_at.strftime("%d/%m/%Y"),
        row.last_movement_title or "",
    )


def build_xlsx(rows: list[LawsuitListRow]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Processos"
    sheet.append(_COLUMNS)
    for row in rows:
        sheet.append(_row_for(row))

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def build_pdf(rows: list[LawsuitListRow]) -> bytes:
    pdf = FPDF(orientation="L")
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)

    col_width = pdf.epw / len(_COLUMNS)
    for column in _COLUMNS:
        pdf.cell(col_width, 8, column, border=1)
    pdf.ln()

    for row in rows:
        for value in _row_for(row):
            pdf.cell(col_width, 8, value, border=1)
        pdf.ln()

    return bytes(pdf.output())
