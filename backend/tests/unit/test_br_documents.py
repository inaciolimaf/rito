from app.core.br_documents import (
    is_valid_cnpj,
    is_valid_cpf,
    is_valid_cpf_or_cnpj,
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
