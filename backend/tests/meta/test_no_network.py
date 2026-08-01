"""Regra 4 da spec 009: nenhum teste (nem o app) faz I/O de rede real."""

import re
from pathlib import Path

import pytest
from pytest_socket import SocketConnectBlockedError

APP_DIR = Path(__file__).resolve().parents[2] / "app"

# Formas comuns de abrir uma conexão de rede sem passar pelo httpx.AsyncClient documentado
# (app/integrations/). Nenhuma integração real existe ainda (LLM/DJEN/DataJud chegam nas
# specs 041+) — este teste é o guarda-corpo que vai pegar a primeira que tentar pular a
# fixture gravada.
_FORBIDDEN_PATTERNS = [
    re.compile(r"\bimport requests\b"),
    re.compile(r"\burllib\.request\b"),
    re.compile(r"\bsocket\.create_connection\b"),
]


def test_pytest_socket_bloqueia_conexao_para_host_nao_liberado() -> None:
    """Prova que o guarda está ativo de verdade, não só configurado."""
    import socket

    with pytest.raises(SocketConnectBlockedError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("93.184.216.34", 80))


def test_nenhum_modulo_da_app_usa_cliente_http_fora_do_padrao() -> None:
    offenders: list[str] = []
    for path in APP_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for pattern in _FORBIDDEN_PATTERNS:
            if pattern.search(text):
                offenders.append(f"{path.relative_to(APP_DIR.parent)}: {pattern.pattern}")

    assert offenders == [], (
        "Uso de cliente de rede fora do padrão (httpx via app/integrations/) encontrado: "
        + ", ".join(offenders)
    )
