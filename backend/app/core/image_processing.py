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


def process_image(content: bytes, content_type: str) -> bytes:
    """Valida e redimensiona uma imagem (logotipo do escritório, spec 011; avatar de
    usuário, spec 012 — mesma regra de negócio nos dois: PNG/JPG/SVG, máx. 2 MB,
    redimensionado a 512px no maior lado).

    SVG é vetorial — não faz sentido "redimensionar" pixels, então passa direto após a
    validação de tipo/tamanho.
    """
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise InvalidImageError("Formato inválido — use PNG, JPG ou SVG.")
    if len(content) > MAX_IMAGE_SIZE_BYTES:
        raise InvalidImageError("Arquivo acima de 2 MB.")

    if content_type == "image/svg+xml":
        return content

    pillow_format = _CONTENT_TYPE_TO_PILLOW_FORMAT[content_type]
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.thumbnail((MAX_IMAGE_DIMENSION_PX, MAX_IMAGE_DIMENSION_PX))
            buffer = io.BytesIO()
            image.save(buffer, format=pillow_format)
            return buffer.getvalue()
    except UnidentifiedImageError as exc:
        # Content-Type é informado pelo cliente e pode mentir — o conteúdo real não
        # decodifica como imagem nenhuma.
        raise InvalidImageError("Arquivo não é uma imagem válida.") from exc
