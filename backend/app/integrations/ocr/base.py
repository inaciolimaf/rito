"""Contrato de OCR (spec 091, regra 1).

OCR é integração, não regra de negócio: o service de extração não sabe se por trás há
Tesseract, um serviço em nuvem ou nada instalado. Pelo DIP do CLAUDE.md §5, ele recebe um
`OcrProvider` — e em teste recebe um fake que implementa o mesmo Protocol, sem processo
externo nenhum.
"""

from dataclasses import dataclass
from typing import Protocol


class OcrError(Exception):
    """Falha ao ler o arquivo. A mensagem vai para a tela (regra 10)."""


class OcrNotConfiguredError(OcrError):
    """Nenhum motor de OCR disponível no servidor — a tela explica em vez de quebrar."""

    def __init__(self) -> None:
        super().__init__(
            "Este servidor não tem OCR instalado, então imagens e PDFs digitalizados não "
            "podem ser lidos. Envie um PDF com texto ou peça ao suporte para habilitar."
        )


@dataclass(frozen=True)
class OcrResult:
    text: str
    page_count: int


class OcrProvider(Protocol):
    """Uma implementação recebe bytes e devolve texto. Nada mais."""

    @property
    def is_available(self) -> bool:
        """Falso quando o motor não está instalado (regra 12: a tela avisa)."""
        ...

    async def extract_text(self, *, content: bytes, content_type: str) -> OcrResult: ...
