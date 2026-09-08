"""Escopos da API pública (spec 095, regra 2).

Um escopo por recurso e operação. A lista é fechada porque escopo inventado seria escopo
que nunca é conferido — e um token com `write:tudo` derrotaria o propósito de existir
escopo.
"""

from typing import Final

READ: Final = "read"
WRITE: Final = "write"

RESOURCES: Final[tuple[str, ...]] = (
    "settings",
    "customers",
    "lawsuits",
    "posts",
    "publications",
    "transactions",
    "documents",
)

# `settings` e `publications` são só leitura na v1 — não existe escrita correspondente na
# API interna que faça sentido expor sem uma spec própria.
WRITABLE: Final[frozenset[str]] = frozenset({"customers", "lawsuits", "posts", "transactions"})

ALL_SCOPES: Final[tuple[str, ...]] = tuple(
    sorted(
        [f"{READ}:{resource}" for resource in RESOURCES]
        + [f"{WRITE}:{resource}" for resource in sorted(WRITABLE)]
    )
)


def is_valid(scope: str) -> bool:
    return scope in ALL_SCOPES


def describe(scope: str) -> str:
    operacao, _, recurso = scope.partition(":")
    verbo = "ler" if operacao == READ else "escrever em"
    return f"{verbo} {recurso}"


# Escopo que cai no eixo FINANCEIRO (spec 005, regra 2: o eixo é ortogonal ao perfil —
# um Gestor pode ter NONE). O mapa vale para os dois lados da mesma pergunta: na emissão
# do token (quem emite não pode delegar o que não tem) e na chamada pública (o dono do
# token pode ter perdido o acesso desde então). Ficar aqui, e não em cada lugar, é o que
# garante que os dois lados usem exatamente a mesma lista.
REQUIRED_CAPABILITY: Final[dict[str, str]] = {
    f"{READ}:transactions": "financial.read",
    f"{WRITE}:transactions": "financial.write",
}


def required_capability(scope: str) -> str | None:
    """A capacidade que o dono do token precisa ter para este escopo valer algo.

    `None` = o escopo se basta. As capacidades são as mesmas de `capabilities_for`
    (`app/core/permissions.py`), de propósito: um eixo de permissão novo entra na matriz
    de lá e passa a valer aqui sem uma segunda tabela para manter em dia.
    """
    return REQUIRED_CAPABILITY.get(scope)


def financial_scopes(scopes: list[str]) -> list[str]:
    """Os escopos financeiros de uma lista — na ordem em que o integrador os pediu."""
    return [scope for scope in scopes if scope in REQUIRED_CAPABILITY]
