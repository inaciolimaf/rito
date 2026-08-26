"""Guarda-corpo contra citação inventada (spec 087, regra 6).

O prompt proíbe citar jurisprudência que não esteja no contexto — mas prompt é pedido,
não garantia. Este módulo é a garantia: depois de gerar, qualquer citação que apareça no
texto e NÃO apareça no contexto coletado é removida e registrada.

A escolha de remover (em vez de só avisar) é deliberada: uma minuta com súmula inventada
que passa batida numa revisão apressada vira petição protocolada com súmula inventada.
O marcador que fica no lugar é impossível de não ver.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

# Padrões de citação que um modelo inventa com facilidade e que um advogado confere com
# dificuldade (número parece número).
_CITATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("súmula", re.compile(r"\bs[úu]mula\s+(?:vinculante\s+)?n?[.º°]?\s*(\d{1,4})", re.IGNORECASE)),
    (
        "recurso",
        re.compile(r"\b(?:REsp|AREsp|RE|AI|AgRg|EDcl)\s*n?[.º°]?\s*([\d.]{4,})", re.IGNORECASE),
    ),
    ("processo", re.compile(r"\b(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})\b")),
)

REMOVED_MARKER = "[citação removida — não consta no processo]"


@dataclass(frozen=True)
class Citation:
    kind: str
    text: str


def find_citations(html: str) -> list[Citation]:
    encontradas: list[Citation] = []
    for kind, pattern in _CITATION_PATTERNS:
        for match in pattern.finditer(html):
            encontradas.append(Citation(kind=kind, text=match.group(0).strip()))
    return encontradas


def _normalize(value: str) -> str:
    return re.sub(r"[^\w]", "", value).lower()


def strip_unsupported_citations(html: str, context: str) -> tuple[str, list[dict[str, str]]]:
    """Devolve o texto sem as citações que não têm respaldo no contexto, e a lista do
    que foi removido.

    A comparação é pelo NÚMERO (normalizado), não pela frase inteira: "Súmula 297 do
    TST" e "súmula nº 297" são a mesma citação, e o que importa é se o 297 está no
    contexto.
    """
    contexto_normalizado = _normalize(context)
    removidas: list[dict[str, str]] = []
    resultado = html

    def _make_replacer(kind: str) -> Callable[[re.Match[str]], str]:
        # `kind` chega por parâmetro (e não da variável do laço) porque a closure só é
        # chamada depois: capturando o laço, toda citação sairia com o último tipo.
        def _replace(match: re.Match[str]) -> str:
            numero = _normalize(match.group(1))
            if numero and numero in contexto_normalizado:
                return match.group(0)
            removidas.append({"kind": kind, "text": match.group(0).strip()})
            return REMOVED_MARKER

        return _replace

    for kind, pattern in _CITATION_PATTERNS:
        resultado = pattern.sub(_make_replacer(kind), resultado)
    return resultado, removidas
