from app.core.export import ExportColumn, TableExport
from app.domain.customers.models import Customer

_EXPORT = TableExport[Customer](
    sheet_title="Contatos",
    columns=[
        ExportColumn("Nome", lambda customer: customer.name),
        ExportColumn("Celular", lambda customer: customer.cellphone or ""),
        ExportColumn("Cidade", lambda customer: customer.city or ""),
        ExportColumn("Data de cadastro", lambda customer: customer.created_at.strftime("%d/%m/%Y")),
    ],
)


def build_xlsx(customers: list[Customer]) -> bytes:
    return _EXPORT.xlsx(customers)


def build_pdf(customers: list[Customer]) -> bytes:
    return _EXPORT.pdf(customers)
