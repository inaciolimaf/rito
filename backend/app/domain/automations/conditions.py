"""Avaliação das condições de uma ação (spec 092, regra 6).

Um mini-avaliador declarativo, e de propósito burro: `{campo, operador, valor}` sobre o
retrato do sujeito que disparou o gatilho. Nada de expressão livre — expressão livre num
campo de configuração é execução de código com outro nome, e quem escreve a automação é
um advogado, não um programador.
"""

from typing import Any

OPERATORS = ("eq", "ne", "gt", "lt", "gte", "lte", "in", "exists", "empty")


class InvalidConditionError(Exception):
    """Condição malformada → 422 na hora de salvar, nunca surpresa na execução."""


def validate_condition(condition: dict[str, Any] | None) -> None:
    if condition is None:
        return
    if not isinstance(condition, dict) or "field" not in condition:
        raise InvalidConditionError("A condição precisa de um campo.")
    operador = condition.get("op", "eq")
    if operador not in OPERATORS:
        raise InvalidConditionError(
            f"Operador desconhecido: {operador}. Use um de: {', '.join(OPERATORS)}."
        )


def evaluate(condition: dict[str, Any] | None, subject: dict[str, Any]) -> bool:
    """Sem condição, a ação roda. É o padrão, e é o que a maioria das automações usa."""
    if not condition:
        return True
    campo = str(condition.get("field", ""))
    operador = str(condition.get("op", "eq"))
    esperado = condition.get("value")
    atual = _lookup(subject, campo)

    if operador == "exists":
        return atual is not None
    if operador == "empty":
        return atual is None or atual == "" or atual == []
    if operador == "in":
        return atual in esperado if isinstance(esperado, list) else False
    if operador == "eq":
        return _same(atual, esperado)
    if operador == "ne":
        return not _same(atual, esperado)
    return _compare(operador, atual, esperado)


def _lookup(subject: dict[str, Any], campo: str) -> Any:
    """`a.b` desce um nível — o payload do gatilho é raso, mas o sujeito aninha."""
    atual: Any = subject
    for parte in campo.split("."):
        if not isinstance(atual, dict):
            return None
        atual = atual.get(parte)
    return atual


def _same(atual: Any, esperado: Any) -> bool:
    # Comparação por texto: o payload vem de JSON, onde um UUID é string e um id do banco
    # é UUID. Comparar tipos crus faria a condição certa falhar silenciosamente.
    if atual is None or esperado is None:
        return atual is esperado
    if isinstance(atual, bool) or isinstance(esperado, bool):
        return bool(atual) is bool(esperado)
    return str(atual) == str(esperado)


def _compare(operador: str, atual: Any, esperado: Any) -> bool:
    try:
        esquerda, direita = float(atual), float(esperado)
    except (TypeError, ValueError):
        # Não numérico: compara como texto (datas ISO ordenam certo assim).
        if atual is None or esperado is None:
            return False
        esquerda, direita = str(atual), str(esperado)  # type: ignore[assignment]
    if operador == "gt":
        return bool(esquerda > direita)
    if operador == "lt":
        return bool(esquerda < direita)
    if operador == "gte":
        return bool(esquerda >= direita)
    return bool(esquerda <= direita)
