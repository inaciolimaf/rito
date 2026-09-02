"""OCR pelo Tesseract, chamado como processo (spec 091).

Fica em `integrations/` porque é exatamente o tipo de coisa que a arquitetura manda
isolar: um binário externo, que pode não existir, com saída em texto puro. O service de
extração fala com o Protocol, nunca com este arquivo.

Chamamos o CLI em vez de amarrar um binding Python de propósito: o binding continua
exigindo o mesmo binário do sistema e ainda acrescenta uma dependência que quebra no
build quando a versão muda. `shutil.which` responde a pergunta que importa — está
instalado? — sem custo nenhum.
"""

import asyncio
import shutil
import tempfile
from pathlib import Path

from app.integrations.ocr.base import OcrError, OcrNotConfiguredError, OcrResult

# Português primeiro: o corpus é RG, contrato e procuração brasileiros. `por+eng` cobre
# o carimbo em inglês que aparece em documento de empresa estrangeira.
_LANGUAGES = "por+eng"
_TIMEOUT_SECONDS = 60
# PDF digitalizado precisa virar imagem antes; `pdftoppm` vem do poppler-utils.
_PDF_DPI = "200"


class TesseractOcr:
    """Implementação de `OcrProvider` sobre o binário do Tesseract."""

    def __init__(self, *, binary: str = "tesseract", pdf_renderer: str = "pdftoppm") -> None:
        self._binary = binary
        self._pdf_renderer = pdf_renderer

    @property
    def is_available(self) -> bool:
        return shutil.which(self._binary) is not None

    async def extract_text(self, *, content: bytes, content_type: str) -> OcrResult:
        if not self.is_available:
            raise OcrNotConfiguredError
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            if content_type == "application/pdf":
                imagens = await self._render_pdf(content, pasta)
            else:
                origem = pasta / "pagina.img"
                origem.write_bytes(content)
                imagens = [origem]
            partes = [await self._run_tesseract(imagem) for imagem in imagens]
        return OcrResult(text="\n".join(partes).strip(), page_count=len(partes))

    async def _render_pdf(self, content: bytes, pasta: Path) -> list[Path]:
        if shutil.which(self._pdf_renderer) is None:
            raise OcrNotConfiguredError
        origem = pasta / "documento.pdf"
        origem.write_bytes(content)
        await self._run(
            [self._pdf_renderer, "-r", _PDF_DPI, "-png", str(origem), str(pasta / "pagina")]
        )
        # Spec 108: o `glob` varre o diretório, e varrer diretório dentro de corrotina
        # trava o event loop de todas as requisições em voo. Vai para uma thread pelo
        # mesmo `asyncio.to_thread` que `integrations/storage/s3.py` usa no boto3 — a
        # stdlib basta aqui, e `anyio` não é dependência declarada deste projeto.
        return await asyncio.to_thread(lambda: sorted(pasta.glob("pagina-*.png")))

    async def _run_tesseract(self, imagem: Path) -> str:
        saida = await self._run([self._binary, str(imagem), "stdout", "-l", _LANGUAGES])
        return saida.decode("utf-8", errors="replace")

    async def _run(self, comando: list[str]) -> bytes:
        process = await asyncio.create_subprocess_exec(
            *comando,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=_TIMEOUT_SECONDS)
        except TimeoutError as exc:
            process.kill()
            raise OcrError("A leitura do documento demorou demais e foi interrompida.") from exc
        if process.returncode != 0:
            detalhe = stderr.decode("utf-8", errors="replace").strip()[:200]
            raise OcrError(f"Não foi possível ler o documento: {detalhe}")
        return stdout


class UnavailableOcr:
    """Usado quando o servidor não tem OCR: falha com mensagem, nunca em silêncio."""

    @property
    def is_available(self) -> bool:
        return False

    async def extract_text(self, *, content: bytes, content_type: str) -> OcrResult:
        raise OcrNotConfiguredError
