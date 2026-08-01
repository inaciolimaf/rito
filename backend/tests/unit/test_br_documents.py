import pytest

from app.core.br_documents import (
    format_postal_code,
    is_valid_cnpj,
    is_valid_cpf,
    is_valid_cpf_or_cnpj,
    is_valid_phone,
    is_valid_postal_code,
    strip_document_mask,
)


def test_cpf_valido_com_mascara() -> None:
    assert is_valid_cpf("111.444.777-35")


def test_cpf_com_digito_verificador_errado() -> None:
    assert not is_valid_cpf("111.444.777-36")


def test_cpf_com_todos_digitos_iguais_e_invalido() -> None:
    assert not is_valid_cpf("111.111.111-11")


def test_cnpj_valido_com_mascara() -> None:
    assert is_valid_cnpj("11.222.333/0001-81")


def test_cnpj_com_digito_verificador_errado() -> None:
    assert not is_valid_cnpj("11.222.333/0001-82")


def test_cnpj_com_todos_digitos_iguais_e_invalido() -> None:
    assert not is_valid_cnpj("11.111.111/1111-11")


def test_is_valid_cpf_or_cnpj_aceita_os_dois_formatos() -> None:
    assert is_valid_cpf_or_cnpj("111.444.777-35")
    assert is_valid_cpf_or_cnpj("11.222.333/0001-81")


def test_is_valid_cpf_or_cnpj_rejeita_tamanho_invalido() -> None:
    assert not is_valid_cpf_or_cnpj("123")


def test_strip_document_mask_remove_pontuacao() -> None:
    assert strip_document_mask("11.222.333/0001-81") == "11222333000181"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1133334444", True),  # fixo, 10 dígitos, com DDD
        ("(11) 3333-4444", True),  # fixo com máscara
        ("11999998888", True),  # celular, 11 dígitos, terceiro dígito 9
        ("11899998888", False),  # 11 dígitos mas terceiro dígito não é 9
        ("5511999998888", False),  # com DDI (55)
        ("+5511999998888", False),  # com DDI (+)
        ("999998888", False),  # sem DDD (9 dígitos)
        ("123", False),
    ],
)
def test_is_valid_phone(value: str, expected: bool) -> None:
    assert is_valid_phone(value) is expected


def test_is_valid_postal_code_aceita_8_digitos_com_ou_sem_mascara() -> None:
    assert is_valid_postal_code("01310-100")
    assert is_valid_postal_code("01310100")


def test_is_valid_postal_code_rejeita_tamanho_errado() -> None:
    assert not is_valid_postal_code("123")


def test_format_postal_code_normaliza_para_99999_999() -> None:
    assert format_postal_code("01310100") == "01310-100"
    assert format_postal_code("01310-100") == "01310-100"
