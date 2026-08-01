import io

import pytest
from PIL import Image

from app.core.image_processing import (
    MAX_IMAGE_DIMENSION_PX,
    InvalidImageError,
    extension_for,
    process_image,
)


def _png_bytes(size: tuple[int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color="blue").save(buffer, format="PNG")
    return buffer.getvalue()


def test_redimensiona_imagem_grande_para_512px_no_maior_lado() -> None:
    processed = process_image(_png_bytes((1000, 400)), "image/png")

    with Image.open(io.BytesIO(processed)) as image:
        assert max(image.size) == MAX_IMAGE_DIMENSION_PX
        assert image.size[0] > image.size[1]


def test_nao_aumenta_imagem_menor_que_o_limite() -> None:
    processed = process_image(_png_bytes((100, 100)), "image/png")

    with Image.open(io.BytesIO(processed)) as image:
        assert image.size == (100, 100)


def test_svg_passa_direto_sem_redimensionar() -> None:
    svg = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"
    assert process_image(svg, "image/svg+xml") == svg


def test_arquivo_acima_de_2mb_levanta_erro() -> None:
    with pytest.raises(InvalidImageError):
        process_image(b"0" * (2 * 1024 * 1024 + 1), "image/png")


def test_content_type_nao_suportado_levanta_erro() -> None:
    with pytest.raises(InvalidImageError):
        process_image(_png_bytes((10, 10)), "image/gif")


def test_conteudo_que_nao_e_imagem_de_verdade_levanta_erro() -> None:
    with pytest.raises(InvalidImageError):
        process_image(b"isso nao e uma imagem", "image/png")


def test_extension_for_mapeia_content_type() -> None:
    assert extension_for("image/png") == "png"
    assert extension_for("image/jpeg") == "jpg"
    assert extension_for("image/svg+xml") == "svg"
