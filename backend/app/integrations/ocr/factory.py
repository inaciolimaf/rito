"""Montagem do motor de OCR (spec 091).

Mesmo padrão do provider de LLM: um motor para o app inteiro, montado uma vez no
lifespan. Servidor sem Tesseract instalado recebe o `UnavailableOcr`, que falha com uma
mensagem em português em vez de estourar um `FileNotFoundError` de subprocesso.
"""

from app.integrations.ocr.base import OcrProvider
from app.integrations.ocr.tesseract import TesseractOcr, UnavailableOcr


def create_ocr_provider() -> OcrProvider:
    tesseract = TesseractOcr()
    return tesseract if tesseract.is_available else UnavailableOcr()
