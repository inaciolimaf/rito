from io import BytesIO

from fpdf import FPDF
from openpyxl import Workbook

from app.domain.customers.models import Customer

_COLUMNS = ("Nome", "Celular", "Cidade", "Data de cadastro")


def _row_for(customer: Customer) -> tuple[str, str, str, str]:
    return (
        customer.name,
        customer.cellphone or "",
        customer.city or "",
        customer.created_at.strftime("%d/%m/%Y"),
    )


def build_xlsx(customers: list[Customer]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Contatos"
    sheet.append(_COLUMNS)
    for customer in customers:
        sheet.append(_row_for(customer))

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def build_pdf(customers: list[Customer]) -> bytes:
    pdf = FPDF(orientation="L")
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)

    col_width = pdf.epw / len(_COLUMNS)
    for column in _COLUMNS:
        pdf.cell(col_width, 8, column, border=1)
    pdf.ln()

    for customer in customers:
        for value in _row_for(customer):
            pdf.cell(col_width, 8, value, border=1)
        pdf.ln()

    return bytes(pdf.output())
