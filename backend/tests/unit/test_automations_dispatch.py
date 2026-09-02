"""As tabelas de despacho das automações são exaustivas (spec 111, regra 3).

A 106 trocou cadeias de `if/elif` por tabelas de despacho em dezenas de lugares. A troca
paga um preço: o `if/elif` erra alto (cai no `else` e alguém percebe), a tabela erra
baixo — **uma chave esquecida some em silêncio**, porque o `.get()` devolve `None` e o
código segue por um caminho que parecia ser o padrão.

Estes testes cobram, de fora, o que o `mypy` não consegue provar sozinho: um `dict` com
chave `str` não sabe que o universo dela é um enum. Ligar `PLR0912` sem eles seria trocar
ramificação demais por buraco silencioso.
"""

from app.domain.automations.actions import _ACTION_RUNNERS
from app.domain.automations.conditions import (
    _OPERATORS_BY_NAME,
    _ORDER_BY_NAME,
    OPERATORS,
    evaluate,
)
from app.domain.automations.models import ActionKind

# `llm_decision` não está em `_ACTION_RUNNERS` de propósito: `AutomationEngine.advance` a intercepta
# ANTES de chamar `run_action`, porque ela não produz detalhe para registrar — ela escolhe o
# ramo e o laço segue (spec 094). É a única exclusão legítima, e está listada aqui para que
# uma segunda exclusão precise ser justificada em vez de aparecer.
ACOES_TRATADAS_FORA_DA_TABELA = {ActionKind.LLM_DECISION.value}

# Os operadores de ORDEM vivem em `_compare`, não em `_OPERATORS_BY_NAME`: eles convertem os dois
# lados para número (ou texto) antes de comparar, e carregar essa conversão em toda entrada
# da tabela pioraria as outras cinco.
# Lido de `_ORDER_BY_NAME`, não escrito à mão. Até a spec 124 este conjunto era um literal
# aqui — um espelho manual da lógica de `_compare`, que naquela época era um `if/elif` com
# fallback silencioso (dívida 36). Com os de ordem virando tabela no código, o teste passa a
# ler a fonte, e um quinto operador de ordem entra nas contas sem ninguém editar o teste.
OPERADORES_DE_ORDEM = set(_ORDER_BY_NAME)


def test_toda_acao_do_enum_tem_execucao() -> None:
    """Regra 3: `ActionKind` e `_ACTION_RUNNERS` não podem divergir.

    Uma ação nova no enum sem entrada na tabela vira `UnknownActionError` em produção — na
    primeira automação de um cliente que a usar, não no CI. O erro é honesto, mas chega
    tarde demais.
    """
    esperadas = {kind.value for kind in ActionKind} - ACOES_TRATADAS_FORA_DA_TABELA
    faltando = sorted(esperadas - set(_ACTION_RUNNERS))
    assert faltando == [], (
        "ação do enum sem entrada em `_ACTION_RUNNERS` — a automação que a usar "
        "falha em produção:\n  " + "\n  ".join(faltando)
    )


def test_nenhuma_execucao_orfa_na_tabela() -> None:
    """O outro lado: entrada em `_ACTION_RUNNERS` que não corresponde a nenhum valor do enum.

    É código morto que parece vivo — pior que código morto, porque quem lê a tabela conta
    com ele.
    """
    orfas = sorted(set(_ACTION_RUNNERS) - {kind.value for kind in ActionKind})
    assert (
        orfas == []
    ), "entrada em `_ACTION_RUNNERS` sem valor correspondente em ActionKind:\n  " + "\n  ".join(
        orfas
    )


def test_todo_operador_declarado_tem_implementacao() -> None:
    """Regra 3 aplicada ao vocabulário de condições.

    `OPERATORS` é o contrato — é o que a validação aceita e o que o front oferece. Cada um
    tem que cair em `_OPERATORS_BY_NAME` ou em `_compare`.

    Esta é a tabela onde o buraco silencioso doeria mais: o `_compare` termina em
    `return bool(esquerda <= direita)`, ou seja, **operador não reconhecido se comporta
    como `lte`**. Um operador novo em `OPERATORS` sem implementação não levantaria erro
    nenhum — a automação simplesmente decidiria errado, e ninguém saberia. Ver §8 da spec.
    """
    implementados = set(_OPERATORS_BY_NAME) | OPERADORES_DE_ORDEM
    faltando = sorted(set(OPERATORS) - implementados)
    assert faltando == [], (
        "operador declarado em `OPERATORS` sem implementação — cairia no fallback de "
        "`_compare` e se comportaria como `lte`, decidindo errado em silêncio:\n  "
        + "\n  ".join(faltando)
    )


def test_nenhum_operador_implementado_fora_do_contrato() -> None:
    """E nada implementado que `OPERATORS` não declare: seria um operador funcionando sem
    estar documentado nem validado, que é como um contrato vira folclore."""
    extras = sorted((set(_OPERATORS_BY_NAME) | OPERADORES_DE_ORDEM) - set(OPERATORS))
    assert extras == [], "operador implementado e não declarado em `OPERATORS`:\n  " + "\n  ".join(
        extras
    )


def test_operador_desconhecido_nao_satisfaz_a_condicao() -> None:
    """Dívida 36: um operador fora da lista decidia como `lte`, em silêncio.

    O caminho existia mesmo com os nove operadores declarados implementados — bastava alguém
    apagar o teste de exaustividade acima para um décimo passar a decidir por «menor ou igual»
    dentro de uma automação. Este teste fecha o CAMINHO, não o estado.

    Os valores revelam o defeito antigo de propósito: `1 <= 2` é verdadeiro, então a condição
    passaria a ser satisfeita se o fallback voltasse.
    """
    assert evaluate({"field": "n", "op": "operador_que_nao_existe", "value": 2}, {"n": 1}) is False


def test_operadores_de_ordem_continuam_decidindo() -> None:
    """A contraprova: os quatro de ordem seguem funcionando.

    Sem ele, trocar o corpo de `_compare` por um `return False` cego passaria — e a correção
    da dívida 36 teria quebrado os operadores que funcionavam.
    """
    assert evaluate({"field": "n", "op": "lte", "value": 2}, {"n": 1}) is True
    assert evaluate({"field": "n", "op": "lt", "value": 2}, {"n": 1}) is True
    assert evaluate({"field": "n", "op": "gt", "value": 2}, {"n": 1}) is False
    assert evaluate({"field": "n", "op": "gte", "value": 1}, {"n": 1}) is True
