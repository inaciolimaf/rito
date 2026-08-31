"""Export tabular genérico (spec 030, alvo 2): xlsx e pdf a partir de colunas tipadas —
extraído dos exports de contatos (019) e processos (027), que repetiam a mesma
construção de workbook/PDF célula a célula.

Uso: cada domínio declara suas `ExportColumn` (cabeçalho + como extrair o valor da
linha) e chama `TableExport(...).xlsx(rows)` / `.pdf(rows)`. A montagem da linha (o que
vai em cada coluna) fica no domínio; a mecânica do arquivo fica aqui.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from io import BytesIO


@dataclass(frozen=True)
class ExportColumn[T]:
    header: str
    value: Callable[[T], str]


class TableExport[T]:
    """xlsx/pdf de uma listagem, respeitando as linhas já filtradas (não a página
    visível — o limite de linhas é decisão do domínio, ex.: EXPORT_ROW_LIMIT)."""

    def __init__(self, *, sheet_title: str, columns: Sequence[ExportColumn[T]]) -> None:
        self.sheet_title = sheet_title
        self.columns = list(columns)

    def _rows(self, items: Iterable[T]) -> list[list[str]]:
        return [[column.value(item) for column in self.columns] for item in items]

    def xlsx(self, items: Iterable[T]) -> bytes:
        # Spec 104: 36 ms de import que só o export de planilha usa.
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        assert sheet is not None
        sheet.title = self.sheet_title
        sheet.append([column.header for column in self.columns])
        for row in self._rows(items):
            sheet.append(row)

        buffer = BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()

    def pdf(self, items: Iterable[T]) -> bytes:
        # Spec 104: 117 ms de import que só o export em PDF usa.
        from fpdf import FPDF

        pdf = FPDF(orientation="L")
        pdf.add_page()
        pdf.set_font("Helvetica", size=10)

        col_width = pdf.epw / len(self.columns)
        for column in self.columns:
            pdf.cell(col_width, 8, column.header, border=1)
        pdf.ln()

        for row in self._rows(items):
            for value in row:
                pdf.cell(col_width, 8, value, border=1)
            pdf.ln()

        return bytes(pdf.output())
