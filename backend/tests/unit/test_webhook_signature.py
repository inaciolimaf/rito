"""Assinatura do webhook (spec 093, regra 2).

Unitário porque é a única parte do webhook que o CLIENTE também implementa: o exemplo
que vai na documentação é literalmente este cálculo, e ele precisa fechar dos dois lados.
"""

from app.domain.webhooks.signature import generate_secret, sign, verify


def test_assinatura_e_verificavel_com_o_mesmo_segredo() -> None:
    secret = generate_secret()
    corpo = b'{"event":"task.completed"}'

    assinatura = sign(secret=secret, body=corpo, timestamp=1_800_000_000)

    assert assinatura.startswith("sha256=")
    assert verify(secret=secret, body=corpo, timestamp=1_800_000_000, signature=assinatura)


def test_corpo_alterado_invalida_a_assinatura() -> None:
    secret = generate_secret()
    assinatura = sign(secret=secret, body=b'{"amount":100}', timestamp=1)

    assert not verify(secret=secret, body=b'{"amount":999}', timestamp=1, signature=assinatura)


def test_timestamp_faz_parte_do_que_e_assinado() -> None:
    """É o que impede replay: a mesma mensagem em outro instante tem outra assinatura."""
    secret = generate_secret()
    corpo = b"{}"

    assert sign(secret=secret, body=corpo, timestamp=1) != sign(
        secret=secret, body=corpo, timestamp=2
    )


def test_outro_segredo_nao_verifica() -> None:
    corpo = b"{}"
    assinatura = sign(secret=generate_secret(), body=corpo, timestamp=1)

    assert not verify(secret=generate_secret(), body=corpo, timestamp=1, signature=assinatura)


def test_segredo_gerado_e_longo_e_identificavel() -> None:
    """O prefixo existe para quem vaza um segredo num log conseguir reconhecê-lo."""
    secret = generate_secret()

    assert secret.startswith("whsec_")
    assert len(secret) > 40
