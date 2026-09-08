"""Comportamento dos nove operadores de condição (spec 132).

O `test_automations_dispatch.py` prova que a **tabela** está completa: todo operador
declarado em `OPERATORS` tem entrada em `_OPERATORS_BY_NAME` ou em `_ORDER_BY_NAME`. Isso é
presença, não comportamento — a lambda por trás da chave pode fazer a coisa errada e o teste
de exaustividade continua verde. A cobertura de linha também: o `dict` literal executa no
import, então as cinco lambdas contam como cobertas sem que nenhuma tenha rodado.

A medição de mutação da spec 132 deu o número: dos nove operadores, só os quatro de ORDEM
eram executados por algum teste, e três deles sem o caso de borda (valores iguais). `eq`,
`ne`, `in`, `exists` e `empty` — os cinco que decidem igualdade e presença — nunca rodavam.
`validate_condition`, que é o 422 na hora de salvar, também não.

Cada teste aqui mata pelo menos um mutante que sobreviveu; a tabela está no §9 da spec 132.
"""

import logging
import uuid

import pytest

from app.domain.automations.conditions import (
    OPERATORS,
    InvalidConditionError,
    evaluate,
    validate_condition,
)


def test_eq_compara_por_texto_e_nao_por_identidade() -> None:
    """A razão de `_same` existir: o payload do gatilho vem de JSON, onde um id é string,
    e o sujeito vem do banco, onde ele é `UUID`. Comparar tipos crus faria a condição certa
    falhar em silêncio — que é o defeito que o comentário do módulo descreve."""
    identificador = uuid.uuid4()

    assert (
        evaluate({"field": "id", "op": "eq", "value": str(identificador)}, {"id": identificador})
        is True
    )
    assert (
        evaluate({"field": "id", "op": "eq", "value": str(uuid.uuid4())}, {"id": identificador})
        is False
    )


def test_eq_com_none_de_um_lado_ou_dos_dois() -> None:
    """Campo ausente no sujeito vira `None`, e `None == None` é a condição «não preenchido»."""
    assert evaluate({"field": "x", "op": "eq", "value": None}, {"x": None}) is True
    assert evaluate({"field": "x", "op": "eq", "value": None}, {"x": "a"}) is False
    assert evaluate({"field": "x", "op": "eq", "value": "a"}, {}) is False
    # Ausente NÃO é `false`: sem esta linha, o ramo de `None` podia cair no de booleano,
    # onde `bool(None) is bool(False)` é verdadeiro e a automação dispararia.
    assert evaluate({"field": "x", "op": "eq", "value": False}, {}) is False


def test_eq_com_booleano_de_um_lado_compara_como_booleano() -> None:
    """`1` e `true` são o mesmo valor para quem escreveu a automação; `"1" == "True"` não."""
    assert evaluate({"field": "ativo", "op": "eq", "value": True}, {"ativo": 1}) is True
    assert evaluate({"field": "ativo", "op": "eq", "value": True}, {"ativo": 0}) is False


def test_ne_e_a_negacao_de_eq() -> None:
    assert evaluate({"field": "x", "op": "ne", "value": "a"}, {"x": "b"}) is True
    assert evaluate({"field": "x", "op": "ne", "value": "a"}, {"x": "a"}) is False


def test_exists_olha_presenca_e_nao_verdade() -> None:
    """`exists` é sobre o campo estar preenchido — `0`, `""` e `false` EXISTEM."""
    assert evaluate({"field": "x", "op": "exists"}, {"x": 0}) is True
    assert evaluate({"field": "x", "op": "exists"}, {"x": None}) is False
    assert evaluate({"field": "x", "op": "exists"}, {}) is False


def test_empty_cobre_none_texto_vazio_e_lista_vazia() -> None:
    assert evaluate({"field": "x", "op": "empty"}, {"x": None}) is True
    assert evaluate({"field": "x", "op": "empty"}, {"x": ""}) is True
    assert evaluate({"field": "x", "op": "empty"}, {"x": []}) is True
    assert evaluate({"field": "x", "op": "empty"}, {"x": "algo"}) is False


def test_in_exige_lista_do_lado_esperado() -> None:
    """Valor que não é lista NÃO satisfaz — `in` sobre string casaria substring, e uma
    automação de «fase está em [X, Y]» passaria a disparar por pedaço de palavra."""
    assert evaluate({"field": "x", "op": "in", "value": ["a", "b"]}, {"x": "a"}) is True
    assert evaluate({"field": "x", "op": "in", "value": ["a", "b"]}, {"x": "c"}) is False
    assert evaluate({"field": "x", "op": "in", "value": "abc"}, {"x": "a"}) is False


def test_operadores_de_ordem_na_borda_de_valores_iguais() -> None:
    """A borda é o que separa `gt` de `gte`. Sem ela, os dois pares são indistinguíveis —
    e trocar `>` por `>=` numa automação de prazo é um dia inteiro de diferença."""
    assert evaluate({"field": "n", "op": "gt", "value": 5}, {"n": 5}) is False
    assert evaluate({"field": "n", "op": "lt", "value": 5}, {"n": 5}) is False
    assert evaluate({"field": "n", "op": "gte", "value": 5}, {"n": 5}) is True
    assert evaluate({"field": "n", "op": "lte", "value": 5}, {"n": 5}) is True


def test_ordem_com_none_de_qualquer_lado_nao_satisfaz() -> None:
    """Sem isto, a comparação cai no ramo de texto e `"None" > "AAA"` decide a automação —
    a mesma família de defeito da dívida 36: comparar o que não dá para comparar."""
    assert evaluate({"field": "x", "op": "gt", "value": "AAA"}, {"x": None}) is False
    assert evaluate({"field": "x", "op": "gt", "value": None}, {"x": "ZZZ"}) is False


def test_condicao_sem_operador_usa_eq() -> None:
    """`op` é opcional no payload, e o padrão documentado é `eq`."""
    assert evaluate({"field": "x", "value": 1}, {"x": 1}) is True
    assert evaluate({"field": "x", "value": 2}, {"x": 1}) is False


def test_operador_desconhecido_registra_aviso(caplog: pytest.LogCaptureFixture) -> None:
    """O `False` da dívida 36 só é visível porque o aviso existe: a automação que não roda
    aparece no histórico de execuções, mas a CAUSA só aparece no log."""
    caplog.set_level(logging.WARNING, logger="app.domain.automations.conditions")

    assert evaluate({"field": "n", "op": "xpto", "value": 2}, {"n": 1}) is False

    assert any("xpto" in registro.getMessage() for registro in caplog.records)


def test_validate_condition_aceita_ausencia_e_operador_padrao() -> None:
    validate_condition(None)
    validate_condition({"field": "x"})
    validate_condition({"field": "x", "op": "empty"})


def test_validate_condition_exige_campo() -> None:
    with pytest.raises(InvalidConditionError) as exc:
        validate_condition({"op": "eq", "value": 1})

    assert str(exc.value) == "A condição precisa de um campo."


def test_validate_condition_recusa_operador_fora_do_contrato() -> None:
    """A mensagem lista o vocabulário aceito porque ela vai para o 422 de quem está
    montando a automação — dizer só «inválido» obrigaria a abrir o código."""
    with pytest.raises(InvalidConditionError) as exc:
        validate_condition({"field": "x", "op": "xpto"})

    assert str(exc.value) == f"Operador desconhecido: xpto. Use um de: {', '.join(OPERATORS)}."
