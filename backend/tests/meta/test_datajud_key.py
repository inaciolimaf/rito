"""Regra 1 da spec 046: a chave do DataJud vem SEMPRE de `DATAJUD_API_KEY` — uma
chave literal no código de produção reprova este teste (não é lint estático de
verdade, mas o mesmo espírito do guarda de rede em test_no_network.py)."""

from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2] / "app"

# Valor publicado no tutorial oficial da API Pública do Datajud (DPJ/CNJ) — é a
# chave PÚBLICA (regra 2), replicada em .env.example. Nunca deve aparecer
# hardcoded fora de configuração/documentação/fixture.
_PUBLIC_KEY_VALUE = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="


def test_nenhuma_chave_literal_no_codigo_de_producao() -> None:
    offenders = [
        str(path.relative_to(APP_DIR.parent))
        for path in APP_DIR.rglob("*.py")
        if _PUBLIC_KEY_VALUE in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"chave do DataJud hardcoded fora de configuração: {offenders}"


def test_datajud_client_so_le_a_chave_via_settings() -> None:
    """`app/integrations/datajud/client.py` recebe a chave por parâmetro (DIP) —
    nunca importa `app.core.config` para ler `DATAJUD_API_KEY` sozinho; quem
    monta o client a partir de `get_settings()` é o worker/service (spec 047+)."""
    client_source = (APP_DIR / "integrations" / "datajud" / "client.py").read_text(encoding="utf-8")
    assert "get_settings" not in client_source
