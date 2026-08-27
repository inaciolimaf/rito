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
