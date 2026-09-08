"""Export xlsx/pdf da listagem de contatos (spec 019) — colunas do domínio sobre o
`TableExport` genérico (spec 030)."""

from datetime import datetime

from app.core.clock import Clock
from app.core.export import ExportColumn, TableExport
from app.domain.customers.models import Customer


def _office_day_br(instant: datetime, clock: Clock) -> str:
    """`DD/MM/AAAA` do dia em que `instant` caiu **no fuso do escritório** (spec 136).

    `created_at` é `timestamptz`, e `strftime` sobre ele formata o dia de UTC. Na tela a
    mesma coluna passa por `toLocaleDateString("pt-BR")` no browser, que converte: um
    contato cadastrado às 23h47 de 31/08 em São Paulo aparecia como **31/08/2026** na
    listagem e **01/09/2026** na planilha. Duas datas para o mesmo registro não são lidas
    como bug de fuso — são lidas como alguém tendo mexido no cadastro.

    O `CLAUDE.md` §9 manda `DD/MM/AAAA` na UI, e o export cumpria a forma errando o dia.
    """
    return instant.astimezone(clock.timezone).strftime("%d/%m/%Y")


def _export(clock: Clock) -> TableExport[Customer]:
    """As colunas com o fuso preso por fecho — `ExportColumn` só recebe a linha, então o
    fuso precisa entrar por aqui (mesma solução do `today` em `posts/export.py`)."""
    return TableExport[Customer](
        sheet_title="Contatos",
        columns=[
            ExportColumn("Nome", lambda customer: customer.name),
            ExportColumn("Celular", lambda customer: customer.cellphone or ""),
            ExportColumn("Cidade", lambda customer: customer.city or ""),
            ExportColumn(
                "Data de cadastro", lambda customer: _office_day_br(customer.created_at, clock)
            ),
        ],
    )


def build_xlsx(customers: list[Customer], clock: Clock | None = None) -> bytes:
    return _export(clock or Clock()).xlsx(customers)


def build_pdf(customers: list[Customer], clock: Clock | None = None) -> bytes:
    return _export(clock or Clock()).pdf(customers)
