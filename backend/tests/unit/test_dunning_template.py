"""Financeiro: template de cobrança (spec 061, regra 7) — puro, sem banco."""

from datetime import date
from decimal import Decimal

from app.domain.dunning.template import TemplateContext, render_template

_CONTEXT = TemplateContext(
    customer_name="Maria Silva",
    amount=Decimal("1234.56"),
    due_date=date(2026, 8, 10),
    days_overdue=5,
    process_number="0001234-56.2026.8.26.0100",
    tenant_name="Escritório Exemplo",
)


def test_todas_as_6_variaveis_resolvem() -> None:
    template = (
        "Olá {{customer_name}}, o valor {{amount}} venceu em {{due_date}} há "
        "{{days_overdue}} dias (processo {{process_number}}). Att, {{tenant_name}}."
    )
    rendered = render_template(template, _CONTEXT)
    assert rendered == (
        "Olá Maria Silva, o valor R$ 1.234,56 venceu em 10/08/2026 há "
        "5 dias (processo 0001234-56.2026.8.26.0100). Att, Escritório Exemplo."
    )


def test_valor_formata_milhar_e_centavo_em_pt_br() -> None:
    context = TemplateContext(
        customer_name="X",
        amount=Decimal("1000000.05"),
        due_date=date(2026, 1, 1),
        days_overdue=0,
        process_number=None,
        tenant_name="X",
    )
    assert render_template("{{amount}}", context) == "R$ 1.000.000,05"


def test_processo_ausente_vira_string_vazia() -> None:
    context = TemplateContext(
        customer_name="X",
        amount=Decimal("10.00"),
        due_date=date(2026, 1, 1),
        days_overdue=0,
        process_number=None,
        tenant_name="X",
    )
    assert render_template("processo: [{{process_number}}]", context) == "processo: []"


def test_placeholder_desconhecido_passa_direto_sem_quebrar() -> None:
    texto = "Olá {{nome_que_nao_existe}}!"
    assert render_template(texto, _CONTEXT) == texto


def test_texto_sem_chaves_duplas_passa_intacto() -> None:
    texto = "Este e-mail não tem { chave simples } nem variável nenhuma."
    assert render_template(texto, _CONTEXT) == texto
