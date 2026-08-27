"""Peneira de SSRF do webhook (spec 093, regras 6 e 7).

Unitário e sem rede: todos os casos usam IP literal ou nome reservado, que `getaddrinfo`
resolve sem consultar DNS. É de propósito — o teste que protege contra acesso à rede
interna não pode depender de rede.
"""

import pytest

from app.domain.webhooks.ssrf import UnsafeUrlError, validate_webhook_url


def test_https_para_ip_publico_passa() -> None:
    assert validate_webhook_url("https://8.8.8.8/hooks/rito")


@pytest.mark.parametrize(
    "url",
    [
        "https://10.0.0.5/hook",
        "https://192.168.1.10/hook",
        "https://172.16.0.1/hook",
        "https://127.0.0.1/hook",
        "https://[::1]/hook",
    ],
)
def test_ip_privado_e_bloqueado(url: str) -> None:
    """O vetor clássico: a URL é do usuário, e o servidor está dentro da rede."""
    with pytest.raises(UnsafeUrlError):
        validate_webhook_url(url)


def test_metadados_de_nuvem_sao_bloqueados_com_mensagem_propria() -> None:
    """169.254.169.254 devolve credencial de nuvem em texto puro. Merece nome próprio
    na mensagem, para quem configurou entender que não é limitação genérica."""
    with pytest.raises(UnsafeUrlError, match="metadados"):
        validate_webhook_url("https://169.254.169.254/latest/meta-data/")


def test_http_externo_e_recusado() -> None:
    """Regra 6: o payload e a assinatura iriam em texto puro pela rede."""
    with pytest.raises(UnsafeUrlError, match="HTTPS"):
        validate_webhook_url("http://8.8.8.8/hook")


def test_localhost_so_em_desenvolvimento() -> None:
    with pytest.raises(UnsafeUrlError):
        validate_webhook_url("http://localhost:5678/webhook")
    assert validate_webhook_url("http://localhost:5678/webhook", allow_local=True)


def test_esquema_estranho_e_recusado() -> None:
    """`file://` e `gopher://` são as portas dos ataques mais antigos do gênero."""
    for url in ("file:///etc/passwd", "gopher://8.8.8.8/x"):
        with pytest.raises(UnsafeUrlError):
            validate_webhook_url(url)
