"""O substituto do `assert` de produção (spec 115).

Estes testes existem por um motivo específico: `not_none` é a ÚNICA função do projeto cujo
ramo de falha é intestável nos pontos de uso — ele existe justamente onde a condição não
pode acontecer. Cobri-lo aqui é o que permite que os trinta pontos de uso não tenham cada
um o seu ramo morto.
"""

import pytest

from app.core.invariants import InvariantError, not_none


def test_devolve_o_valor_quando_existe() -> None:
    assert not_none(7, "nunca dispara") == 7
    assert not_none("", "string vazia NÃO é None") == ""
    assert not_none(0, "zero NÃO é None") == 0
    assert not_none(False, "False NÃO é None") is False


def test_levanta_com_a_explicacao_quando_e_nulo() -> None:
    """A mensagem é o produto: ela é o que a pessoa de plantão lê no log."""
    with pytest.raises(InvariantError, match="o RLS já filtrou por tenant"):
        not_none(None, "o RLS já filtrou por tenant")


def test_invariant_error_nao_e_erro_de_dominio() -> None:
    """`RuntimeError`, não `ValueError` nem exceção de domínio.

    A distinção importa no handler: erro de domínio vira 4xx e diz ao usuário que ele
    errou; invariante quebrada vira 500 porque quem errou fomos nós. Herdar de
    `RuntimeError` mantém `not_none` fora de qualquer `except ValueError` existente.
    """
    assert issubclass(InvariantError, RuntimeError)
    assert not issubclass(InvariantError, ValueError)


def test_sobrevive_ao_modo_otimizado() -> None:
    """O ponto inteiro da spec 115: `python -O` não apaga esta verificação.

    `assert` vira `pass` sob `-O`; um `if` que levanta, não. O teste compila o mesmo
    código nos dois modos e confirma que só o `assert` some.
    """
    import subprocess
    import sys

    programa = (
        "from app.core.invariants import not_none, InvariantError\n"
        "try:\n"
        "    not_none(None, 'motivo')\n"
        "except InvariantError:\n"
        "    print('levantou')\n"
    )
    for flags in ([], ["-O"]):
        resultado = subprocess.run(
            [sys.executable, *flags, "-c", programa],
            capture_output=True,
            text=True,
            check=True,
        )
        assert resultado.stdout.strip() == "levantou", f"falhou com flags {flags}"
