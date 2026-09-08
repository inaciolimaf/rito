"""Export da tela de Atividades (spec 128, regra 7) — as mesmas linhas que a listagem
devolve, sem a paginação. A mecânica do arquivo é do `core/export.py`; aqui só moram as
colunas."""

from datetime import date

from app.core.export import ExportColumn, TableExport
from app.domain.posts.listing import ActivityListRow, status_of

_STATUS_LABELS = {"PENDENTE": "Pendente", "CONCLUIDA": "Concluída", "ATRASADA": "Atrasada"}


def _br_date(valor: date | None) -> str:
    """`DD/MM/AAAA` (CLAUDE.md §9): a planilha é documento de usuário, não API."""
    return valor.strftime("%d/%m/%Y") if valor is not None else ""


def _lawsuit_label(row: ActivityListRow) -> str:
    """Número do processo quando existe; senão a pasta — o mesmo rótulo da coluna
    "Processo" da tela, para a planilha bater com a tabela."""
    return row.process_number or row.folder or ""


def _columns(today: date) -> list[ExportColumn[ActivityListRow]]:
    """`today` entra por fecho porque o status depende do dia do escritório (`Clock`) e
    `ExportColumn` só recebe a linha — congelar o dia num módulo tornaria a coluna de
    status errada em qualquer processo que vire a meia-noite."""
    return [
        ExportColumn("Tarefa", lambda row: row.task_type_name),
        ExportColumn("Processo", _lawsuit_label),
        ExportColumn("Responsáveis", lambda row: ", ".join(row.assignee_names)),
        ExportColumn("Data do compromisso", lambda row: _br_date(row.post.scheduled_date)),
        ExportColumn("Prazo fatal", lambda row: _br_date(row.post.deadline_date)),
        ExportColumn("Status", lambda row: _STATUS_LABELS[status_of(row, today)]),
    ]


def build_xlsx(rows: list[ActivityListRow], today: date) -> bytes:
    return TableExport(sheet_title="Atividades", columns=_columns(today)).xlsx(rows)


def build_pdf(rows: list[ActivityListRow], today: date) -> bytes:
    return TableExport(sheet_title="Atividades", columns=_columns(today)).pdf(rows)
