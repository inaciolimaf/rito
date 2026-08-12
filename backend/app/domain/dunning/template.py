"""Resolução de variáveis do template de cobrança (spec 061, regra 7) — puro, sem
banco, testável isolado (mesmo espírito de `app/core/dates.py`)."""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

_PLACEHOLDER_PATTERN = re.compile(r"\{\{(\w+)\}\}")


@dataclass
class TemplateContext:
    customer_name: str
    amount: Decimal
    due_date: date
    days_overdue: int
    process_number: str | None
    tenant_name: str


def _format_brl(amount: Decimal) -> str:
    """`Decimal` → "R$ 1.234,56" (CLAUDE.md §9: dinheiro em string com vírgula na UI
    brasileira — o e-mail de cobrança é conteúdo pra humano, mesma regra da tela)."""
    quantized = amount.quantize(Decimal("0.01"))
    sign = "-" if quantized < 0 else ""
    integer_part, _, decimal_part = f"{abs(quantized):.2f}".partition(".")
    groups: list[str] = []
    while len(integer_part) > 3:
        groups.insert(0, integer_part[-3:])
        integer_part = integer_part[:-3]
    groups.insert(0, integer_part)
    return f"{sign}R$ {'.'.join(groups)},{decimal_part}"


def render_template(template: str, context: TemplateContext) -> str:
    """Substitui `{{variavel}}` pelos 6 valores da regra 7 — placeholder desconhecido
    ou texto sem chaves duplas passa direto, sem levantar erro (o template é texto
    livre digitado pelo usuário, nunca deve quebrar o envio)."""
    values = {
        "customer_name": context.customer_name,
        "amount": _format_brl(context.amount),
        "due_date": context.due_date.strftime("%d/%m/%Y"),
        "days_overdue": str(context.days_overdue),
        "process_number": context.process_number or "",
        "tenant_name": context.tenant_name,
    }

    def replace(match: re.Match[str]) -> str:
        return values.get(match.group(1), match.group(0))

    return _PLACEHOLDER_PATTERN.sub(replace, template)
