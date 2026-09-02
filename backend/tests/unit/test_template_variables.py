"""Engine de variáveis (spec 066, §8) — extenso e `resolve_content` puros, sem
banco: cobrem as regras 4/5/6 sem pagar o custo de uma query."""

from collections.abc import Mapping
from datetime import date
from decimal import Decimal

from app.domain.templates.variables import (
    _ACCOUNT_FIELDS,
    _CUSTOMER_FIELDS,
    _LAWSUIT_FIELDS,
    _RESOLVERS,
    _USER_FIELDS,
    VARIABLE_CATALOG,
    format_date_extenso,
    format_money_extenso,
    resolve_content,
)


def test_extenso_de_data_usa_primeiro_no_dia_1() -> None:
    assert format_date_extenso(date(2026, 8, 1)) == "primeiro de agosto de dois mil e vinte e seis"


def test_extenso_de_data_cardinal_nos_demais_dias() -> None:
    assert format_date_extenso(date(2026, 8, 20)) == "vinte de agosto de dois mil e vinte e seis"


def test_extenso_de_dinheiro_com_reais_e_centavos() -> None:
    result = format_money_extenso(Decimal("1234.56"))
    assert "reais" in result
    assert "cinquenta e seis centavos" in result


def test_extenso_de_dinheiro_valor_inteiro_sem_centavos_residuais() -> None:
    result = format_money_extenso(Decimal("1.00"))
    assert result == "um real"


def test_resolve_content_substitui_variavel_conhecida() -> None:
    html, missing = resolve_content(
        "<p>Olá {{cliente.nome_completo}}</p>", {"cliente.nome_completo": "Maria Silva"}
    )
    assert html == "<p>Olá Maria Silva</p>"
    assert missing == []


def test_resolve_content_marca_variavel_desconhecida_sem_quebrar_as_outras() -> None:
    html, missing = resolve_content(
        "<p>{{cliente.nome_completo}} — {{cliente.campo_inventado}}</p>",
        {"cliente.nome_completo": "Maria Silva"},
    )
    assert "Maria Silva" in html
    assert '<mark data-missing="true">{{cliente.campo_inventado}}</mark>' in html
    assert missing == ["cliente.campo_inventado"]


def test_resolve_content_variavel_sem_dado_vira_mark_e_e_reportada() -> None:
    html, missing = resolve_content("<p>{{processo.numero_cnj}}</p>", {"processo.numero_cnj": None})
    assert '<mark data-missing="true">{{processo.numero_cnj}}</mark>' in html
    assert missing == ["processo.numero_cnj"]


def test_resolve_content_texto_fora_do_padrao_fica_intocado() -> None:
    html, missing = resolve_content("<p>{{ isso não é variável }}</p>", {})
    assert html == "<p>{{ isso não é variável }}</p>"
    assert missing == []


# ------------------------------------------------------------------ spec 111, regra 3
#
# O catálogo e os resolvedores são duas listas que precisam concordar. A 106 transformou
# `_resolve_customer` e `_resolve_lawsuit` — cadeias de 16 `if` cada — em `_CUSTOMER_FIELDS`
# e `_LAWSUIT_FIELDS`. Depois disso, catálogo e tabela podem divergir em silêncio nos dois
# sentidos, e cada sentido tem um estrago diferente.


def test_toda_variavel_do_catalogo_tem_resolvedor() -> None:
    """Regra 1 da 066 vista pelo avesso: o catálogo é o que o front OFERECE no seletor.

    Uma variável publicada sem resolvedor não estoura: `build_variable_map` a mapeia para
    `None` e `resolve_content` a marca como faltante. O usuário escolhe a variável no
    seletor, insere no modelo, gera o documento e encontra um `<mark>` no lugar do dado —
    sem nenhum erro em lugar nenhum. É o pior desfecho possível: silencioso e visível para
    o cliente do escritório.
    """
    # `Mapping[str, object]` porque as quatro tabelas têm tipos de VALOR diferentes
    # (`_CustomerField`, `_LawsuitField`, ...); aqui só se pergunta pelas CHAVES.
    tabelas: dict[str, Mapping[str, object]] = {
        "cliente": _CUSTOMER_FIELDS,
        "processo": _LAWSUIT_FIELDS,
        "escritorio": _ACCOUNT_FIELDS,
        "usuario": _USER_FIELDS,
    }
    sem_resolvedor = sorted(
        f"{namespace}.{campo}"
        for namespace, campo, _rotulo in VARIABLE_CATALOG
        if campo not in tabelas[namespace]
    )
    assert sem_resolvedor == [], (
        "variável publicada no catálogo e sem resolvedor — vira <mark> no documento "
        "gerado, sem erro:\n  " + "\n  ".join(sem_resolvedor)
    )


def test_todo_resolvedor_esta_publicado_no_catalogo() -> None:
    """O outro sentido: resolvedor que ninguém pode escolher.

    Não quebra nada — e é justamente por isso que fica. `{{cliente.campo_secreto}}`
    digitado à mão funcionaria, o que faz do catálogo uma meia-verdade.
    """
    orfaos: list[str] = []
    for namespace, tabela in (
        ("cliente", _CUSTOMER_FIELDS),
        ("processo", _LAWSUIT_FIELDS),
        ("escritorio", _ACCOUNT_FIELDS),
        ("usuario", _USER_FIELDS),
    ):
        publicados = {campo for ns, campo, _ in VARIABLE_CATALOG if ns == namespace}
        orfaos += [f"{namespace}.{campo}" for campo in sorted(set(tabela) - publicados)]
    assert orfaos == [], (
        "resolvedor sem entrada no catálogo — funciona se digitado à mão e não aparece "
        "no seletor:\n  " + "\n  ".join(orfaos)
    )


def test_todo_namespace_do_catalogo_tem_resolvedor() -> None:
    """`build_variable_map` indexa `_RESOLVERS[namespace]` sem `.get()`.

    Um namespace novo no catálogo sem resolvedor levanta `KeyError` na primeira geração de
    documento — e derruba a resolução INTEIRA, não só aquela variável. Este é o único dos
    três que falha alto; ainda assim falha em produção, não aqui.
    """
    faltando = sorted({namespace for namespace, _, _ in VARIABLE_CATALOG} - set(_RESOLVERS))
    assert (
        faltando == []
    ), "namespace do catálogo sem resolvedor — KeyError na geração:\n  " + "\n  ".join(faltando)
