"""Resolução pura de `@menções` (spec 035, regra 1) — sem banco.

O corpo do comentário carrega `@Nome Completo` em texto livre (o autocomplete da UI
insere o nome como o usuário escolheu). A resolução casa os nomes dos usuários ATIVOS
do tenant contra o texto, sem diferenciar acento nem caixa; nomes mais longos casam
primeiro, e o caractere seguinte ao nome não pode ser letra (`@Ana` não menciona
"Ana" dentro de `@Anabela`).
"""

import unicodedata
import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class MentionCandidate:
    """O mínimo que o parser precisa saber de um usuário."""

    user_id: uuid.UUID
    name: str


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def _is_boundary(text: str, end: int) -> bool:
    if end >= len(text):
        return True
    return not text[end].isalpha()


def resolve_mentions(body: str, candidates: list[MentionCandidate]) -> list[uuid.UUID]:
    """Ids dos usuários mencionados no corpo, na ordem em que aparecem no texto.

    Dois usuários com o MESMO nome são mencionados juntos (não há como distinguir em
    texto livre — a UI evita duplicados de nome no autocomplete).
    """
    normalized_body = _normalize(body)
    mentions: list[tuple[int, uuid.UUID]] = []
    ordered = sorted(candidates, key=lambda item: len(item.name), reverse=True)
    for candidate in ordered:
        needle = f"@{_normalize(candidate.name)}"
        start = normalized_body.find(needle)
        if start >= 0 and _is_boundary(normalized_body, start + len(needle)):
            mentions.append((start, candidate.user_id))
    mentions.sort(key=lambda item: item[0])
    # Dedup preservando a ordem de aparição (mesmo usuário citado 2× notifica 1×).
    return list(dict.fromkeys(user_id for _pos, user_id in mentions))
