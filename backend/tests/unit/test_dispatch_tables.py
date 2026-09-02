"""Exaustividade das tabelas com chave fechada (spec 111, regra 3).

O aceite da 111 no `ROADMAP.md` pede «teste que prova a exaustividade de cada tabela». As
das automações e as de variáveis de modelo ficam nos arquivos do próprio domínio
(`test_automations_dispatch.py`, `test_template_variables.py`); aqui ficam as demais — as
que mapeiam um universo **fechado** (um enum ou um `Literal`) para configuração.

Por que não basta o `mypy`: ele checa que a CHAVE usada é do tipo certo, não que TODAS as
chaves do tipo estão presentes. `dict[UserRole, int]` com dois dos três papéis é um tipo
perfeitamente válido — e um `KeyError` esperando o terceiro papel fazer login.
"""

from typing import get_args

from app.core.permissions import (
    _FINANCIAL_CAPABILITIES,
    _FINANCIAL_ORDER,
    _ROLE_CAPABILITIES,
    _ROLE_ORDER,
    FinancialAccess,
    UserRole,
)
from app.domain.dunning.repository import _AGING_RANGES
from app.domain.dunning.schemas import AgingBucket
from app.domain.reports.schemas import REPORT_KEYS, ReportKey
from app.domain.reports.tabular_service import _EXPORT_COLUMNS


def test_todo_papel_tem_ordem_e_capacidades() -> None:
    """As duas tabelas de `UserRole` decidem autorização.

    Um papel ausente em `_ROLE_ORDER` derruba `require_role` com `KeyError`; ausente em
    `_ROLE_CAPABILITIES`, o `mypy` até aceita, e o usuário perde silenciosamente toda
    capacidade — que é o modo de falhar mais perigoso dos dois, porque parece política.
    """
    papeis = set(UserRole)
    assert set(_ROLE_ORDER) == papeis, f"_ROLE_ORDER: falta {sorted(papeis - set(_ROLE_ORDER))}"
    assert (
        set(_ROLE_CAPABILITIES) == papeis
    ), f"_ROLE_CAPABILITIES: falta {sorted(papeis - set(_ROLE_CAPABILITIES))}"


def test_todo_nivel_financeiro_tem_ordem_e_capacidades() -> None:
    """Mesma coisa para `FinancialAccess`, que é a segunda dimensão da autorização: o
    acesso ao financeiro é ortogonal ao papel (spec 013)."""
    niveis = set(FinancialAccess)
    assert (
        set(_FINANCIAL_ORDER) == niveis
    ), f"_FINANCIAL_ORDER: falta {sorted(niveis - set(_FINANCIAL_ORDER))}"
    assert (
        set(_FINANCIAL_CAPABILITIES) == niveis
    ), f"_FINANCIAL_CAPABILITIES: falta {sorted(niveis - set(_FINANCIAL_CAPABILITIES))}"


def test_toda_faixa_de_aging_tem_intervalo() -> None:
    """`AgingBucket` é um `Literal`, e `get_args` devolve o universo dele.

    Faixa sem intervalo em `_AGING_RANGES` não some da resposta: ela aparece zerada, e um
    relatório de inadimplência que mostra R$ 0,00 numa faixa que tem dívida é pior que um
    relatório que falha.
    """
    faixas = set(get_args(AgingBucket))
    assert (
        set(_AGING_RANGES) == faixas
    ), f"_AGING_RANGES: falta {sorted(faixas - set(_AGING_RANGES))}"


def test_todo_relatorio_exportavel_tem_colunas() -> None:
    """Sem entrada em `_EXPORT_COLUMNS`, o relatório existe na tela e o export sai vazio.

    `REPORT_KEYS` e o `Literal ReportKey` também são checados um contra o outro: são duas
    declarações do mesmo universo, e nada além deste teste as obriga a concordar.
    """
    chaves = set(REPORT_KEYS)
    assert chaves == set(get_args(ReportKey)), "REPORT_KEYS e ReportKey divergiram"
    assert (
        set(_EXPORT_COLUMNS) == chaves
    ), f"_EXPORT_COLUMNS: falta {sorted(chaves - set(_EXPORT_COLUMNS))}"
