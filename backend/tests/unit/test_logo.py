import io

import pytest
from PIL import Image

from app.domain.account.exceptions import InvalidLogoError
from app.domain.account.logo import MAX_LOGO_DIMENSION_PX, extension_for, process_logo


def _png_bytes(size: tuple[int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color="blue").save(buffer, format="PNG")
    return buffer.getvalue()


def test_redimensiona_imagem_grande_para_512px_no_maior_lado() -> None:
    processed = process_logo(_png_bytes((1000, 400)), "image/png")

    with Image.open(io.BytesIO(processed)) as image:
        assert max(image.size) == MAX_LOGO_DIMENSION_PX
        assert image.size[0] > image.size[1]


def test_nao_aumenta_imagem_menor_que_o_limite() -> None:
    processed = process_logo(_png_bytes((100, 100)), "image/png")

    with Image.open(io.BytesIO(processed)) as image:
        assert image.size == (100, 100)


def test_svg_passa_direto_sem_redimensionar() -> None:
    svg = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"
    assert process_logo(svg, "image/svg+xml") == svg


def test_arquivo_acima_de_2mb_levanta_erro() -> None:
    with pytest.raises(InvalidLogoError):
        process_logo(b"0" * (2 * 1024 * 1024 + 1), "image/png")


def test_content_type_nao_suportado_levanta_erro() -> None:
    with pytest.raises(InvalidLogoError):
        process_logo(_png_bytes((10, 10)), "image/gif")


def test_conteudo_que_nao_e_imagem_de_verdade_levanta_erro() -> None:
    with pytest.raises(InvalidLogoError):
        process_logo(b"isso nao e uma imagem", "image/png")


def test_extension_for_mapeia_content_type() -> None:
    assert extension_for("image/png") == "png"
    assert extension_for("image/jpeg") == "jpg"
    assert extension_for("image/svg+xml") == "svg"
