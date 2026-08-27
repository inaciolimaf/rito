"""Spec 097, regra 3: nenhum segredo e nenhuma PII saem no log.

Os casos aqui são a lista da regra 3, um por um. Cada asserção tem duas metades: o dado
sensível **sumiu** e o resto da mensagem **ficou** — mascarar apagando a linha inteira
resolveria o vazamento e destruiria o log.
"""

from app.core.observability.redaction import MASK, redact_text, redact_value


def test_senha_token_e_chave_de_api_somem_do_texto() -> None:
    texto = "login falhou password=hunter2 token: eyJhbGciOi.YWJj.ZGVm api_key=sk-live-123"

    saida = redact_text(texto)

    assert "hunter2" not in saida
    assert "sk-live-123" not in saida
    assert "eyJhbGciOi.YWJj.ZGVm" not in saida
    assert "login falhou" in saida


def test_bearer_do_header_nao_vaza() -> None:
    saida = redact_text("Authorization: Bearer abc.def.ghi")

    assert "abc.def.ghi" not in saida
    assert MASK in saida


def test_cpf_cnpj_email_e_telefone_sao_mascarados() -> None:
    texto = (
        "cliente Ana, CPF 529.982.247-25, CNPJ 11.222.333/0001-81, "
        "ana@escritorio.com.br, (11) 98765-4321"
    )

    saida = redact_text(texto)

    assert "529.982.247-25" not in saida
    assert "11.222.333/0001-81" not in saida
    assert "ana@escritorio.com.br" not in saida
    assert "98765-4321" not in saida
    assert "cliente Ana" in saida


def test_cpf_e_cnpj_sem_pontuacao_tambem_somem() -> None:
    saida = redact_text("documentos 52998224725 e 11222333000181 conferidos")

    assert "52998224725" not in saida
    assert "11222333000181" not in saida
    assert "conferidos" in saida


def test_uuid_nao_e_confundido_com_cpf() -> None:
    """Um UUID em cada cem tem 11 dígitos seguidos em algum lugar. Se a redação varresse
    por formato sem olhar as bordas, o `request_id` do log viraria `***` de vez em
    quando — e o campo que existe para correlacionar perderia justamente essa serventia.
    """
    uuid_com_digitos = "12345678901-e89b-12d3-a456-426614174000"

    assert redact_text(f"tenant {uuid_com_digitos} carregado") == (
        f"tenant {uuid_com_digitos} carregado"
    )


def test_chave_sensivel_mascara_o_valor_inteiro_seja_qual_for() -> None:
    payload = {"user": "ana", "password": "qualquer coisa", "nested": {"api_key": "abc"}}

    saida = redact_value(payload)

    assert saida == {"user": "ana", "password": MASK, "nested": {"api_key": MASK}}


def test_lista_e_varrida_item_a_item() -> None:
    saida = redact_value(["ok", "ana@escritorio.com.br"])

    assert saida == ["ok", MASK]
