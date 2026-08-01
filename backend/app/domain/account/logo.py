import io

from PIL import Image, UnidentifiedImageError

from app.domain.account.exceptions import InvalidLogoError

MAX_LOGO_SIZE_BYTES = 2 * 1024 * 1024
MAX_LOGO_DIMENSION_PX = 512

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


def extension_for(content_type: str) -> str:
    return _EXTENSION_BY_CONTENT_TYPE[content_type]


def process_logo(content: bytes, content_type: str) -> bytes:
    """Valida e redimensiona o logotipo (spec 011, regra 4).

    SVG é vetorial — não faz sentido "redimensionar" pixels, então passa direto após a
    validação de tipo/tamanho.
    """
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise InvalidLogoError("Formato inválido — use PNG, JPG ou SVG.")
    if len(content) > MAX_LOGO_SIZE_BYTES:
        raise InvalidLogoError("Logotipo acima de 2 MB.")

    if content_type == "image/svg+xml":
        return content

    pillow_format = _CONTENT_TYPE_TO_PILLOW_FORMAT[content_type]
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.thumbnail((MAX_LOGO_DIMENSION_PX, MAX_LOGO_DIMENSION_PX))
            buffer = io.BytesIO()
            image.save(buffer, format=pillow_format)
            return buffer.getvalue()
    except UnidentifiedImageError as exc:
        # Content-Type é informado pelo cliente e pode mentir — o conteúdo real não
        # decodifica como imagem nenhuma.
        raise InvalidLogoError("Arquivo não é uma imagem válida.") from exc
