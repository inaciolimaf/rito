import io

from PIL import Image, UnidentifiedImageError

MAX_IMAGE_SIZE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_DIMENSION_PX = 512

_CONTENT_TYPE_TO_PILLOW_FORMAT = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
}
_ALLOWED_CONTENT_TYPES = frozenset({*_CONTENT_TYPE_TO_PILLOW_FORMAT, "image/svg+xml"})
_EXTENSION_BY_CONTENT_TYPE = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/svg+xml": "svg",
}


class InvalidImageError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def extension_for(content_type: str) -> str:
    return _EXTENSION_BY_CONTENT_TYPE[content_type]


def process_image(
    content: bytes,
    content_type: str,
    *,
    max_size_bytes: int = MAX_IMAGE_SIZE_BYTES,
    max_dimension_px: int = MAX_IMAGE_DIMENSION_PX,
    allowed_content_types: frozenset[str] = _ALLOWED_CONTENT_TYPES,
    invalid_format_message: str = "Formato inválido — use PNG, JPG ou SVG.",
) -> bytes:
    """Valida e redimensiona uma imagem (logotipo do escritório, spec 011; avatar de
    usuário, spec 012; foto de contato, spec 017 — mesma operação nas três, com limites
    próprios por chamador: os padrões aqui são os de logo/avatar, PNG/JPG/SVG a 2 MB/512px;
    a foto de contato passa os seus (PNG/JPG só, 5 MB/400px, regra 6) explicitamente.

    SVG é vetorial — não faz sentido "redimensionar" pixels, então passa direto após a
    validação de tipo/tamanho.
    """
    if content_type not in allowed_content_types:
        raise InvalidImageError(invalid_format_message)
    if len(content) > max_size_bytes:
        raise InvalidImageError(f"Arquivo acima de {max_size_bytes // (1024 * 1024)} MB.")

    if content_type == "image/svg+xml":
        return content

    pillow_format = _CONTENT_TYPE_TO_PILLOW_FORMAT[content_type]
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.thumbnail((max_dimension_px, max_dimension_px))
            buffer = io.BytesIO()
            image.save(buffer, format=pillow_format)
            return buffer.getvalue()
    except UnidentifiedImageError as exc:
        # Content-Type é informado pelo cliente e pode mentir — o conteúdo real não
        # decodifica como imagem nenhuma.
        raise InvalidImageError("Arquivo não é uma imagem válida.") from exc
