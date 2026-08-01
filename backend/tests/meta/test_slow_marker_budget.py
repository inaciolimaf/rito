"""Regra 6 da spec 009: no máx. 5 testes @pytest.mark.slow no projeto, cada um com
comentário justificando por quê (a linha imediatamente acima do decorador)."""

from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent.parent
META_DIR = Path(__file__).resolve().parent
MAX_SLOW_TESTS = 5


def test_no_maximo_5_testes_marcados_slow_e_todos_justificados() -> None:
    offenders_without_comment: list[str] = []
    total_slow = 0

    for path in TESTS_DIR.rglob("test_*.py"):
        # tests/meta/ fica de fora: os próprios arquivos meta citam "@pytest.mark.slow" em
        # docstring/comentário, o que inflaria a contagem sem ser um teste slow de verdade.
        if path.is_relative_to(META_DIR):
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if "@pytest.mark.slow" not in line:
                continue
            total_slow += 1
            previous_line = lines[index - 1] if index > 0 else ""
            if "#" not in previous_line and "#" not in line:
                rel = path.relative_to(TESTS_DIR.parent)
                offenders_without_comment.append(f"{rel}:{index + 1}")

    assert total_slow <= MAX_SLOW_TESTS, (
        f"{total_slow} testes marcados @pytest.mark.slow — máximo é {MAX_SLOW_TESTS} "
        "(spec 009, regra 6)."
    )
    assert (
        offenders_without_comment == []
    ), "Teste @pytest.mark.slow sem comentário explicando o motivo: " + ", ".join(
        offenders_without_comment
    )
