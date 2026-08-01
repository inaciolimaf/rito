"""Wrapper pytest para tests/meta/test_runner.sh — regras 1-2 da spec 009
(scripts/run-tests.sh falha se uma suíte falha ou se o wall-clock estoura o
orçamento). A lógica em si é bash porque testa um script bash; este arquivo só
garante que ela roda junto com `pytest -n auto`, como as demais."""

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "test_runner.sh"


def test_gate_de_run_tests_sh_cobre_falha_e_estouro_de_orcamento() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
