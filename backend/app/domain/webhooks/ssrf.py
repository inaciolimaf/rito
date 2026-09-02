"""Proteção contra SSRF (spec 093, regras 6 e 7).

Webhook configurável pelo usuário é **o** vetor clássico de acesso à rede interna: quem
escreve a URL escolhe para onde o servidor vai conectar, e o servidor está dentro da rede
privada. O endereço mais famoso desse ataque, `169.254.169.254`, devolve credenciais de
nuvem em texto puro.

A validação é na resolução do DNS, não na string: `interno.exemplo.com` pode apontar para
`10.0.0.5`, e um bloqueio por texto não veria nada de errado. Cada redirecionamento passa
pela mesma peneira, porque o destino público pode devolver um `Location` privado.
"""

import ipaddress
import socket
from urllib.parse import urlparse

# Bloqueio explícito, além do que `ipaddress` já classifica como privado.
_BLOCKED_HOSTNAMES = frozenset({"localhost", "metadata.google.internal"})
# Metadados de nuvem: AWS/GCP/Azure usam o mesmo link-local.
_CLOUD_METADATA = frozenset({"169.254.169.254", "fd00:ec2::254"})


class UnsafeUrlError(Exception):
    """URL recusada. A mensagem vai para a tela de quem configurou (regra 6)."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def validate_webhook_url(url: str, *, allow_local: bool = False) -> str:
    """Devolve a URL se ela for segura; levanta `UnsafeUrlError` se não for.

    `allow_local` existe para o desenvolvimento (regra 6): quem está testando com um n8n
    em `localhost` precisa que funcione. Em produção o flag é falso, e o padrão é o
    seguro — nunca o contrário.
    """
    host = _host_seguro(url, allow_local=allow_local)
    if host is None:  # localhost liberado em desenvolvimento — não resolve DNS
        return url
    _recusar_enderecos_internos(host)
    return url


def _host_seguro(url: str, *, allow_local: bool) -> str | None:
    """Valida esquema e host. Devolve `None` quando é um local liberado (regra 6) — nesse
    caso não há o que resolver, o destino é a própria máquina."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError("A URL do webhook precisa começar com https://.")
    host = parsed.hostname
    if not host:
        raise UnsafeUrlError("A URL do webhook não tem um host válido.")

    eh_local = host in _BLOCKED_HOSTNAMES or host.startswith("127.")
    if parsed.scheme == "http" and not (allow_local and eh_local):
        # Regra 6: HTTP manda o payload e a assinatura em texto puro pela rede.
        raise UnsafeUrlError(
            "Webhook precisa ser HTTPS. HTTP só é aceito para localhost, em desenvolvimento."
        )
    if not eh_local:
        return host
    if allow_local:
        return None
    raise UnsafeUrlError("Endereços locais não são aceitos como destino de webhook.")


def _recusar_enderecos_internos(host: str) -> None:
    """O host resolve para onde? É aqui que o SSRF é barrado de verdade: um nome público
    pode apontar para 169.254.169.254 ou para a rede interna."""
    for endereco in _resolve(host):
        if str(endereco) in _CLOUD_METADATA:
            raise UnsafeUrlError(
                "Este endereço é o serviço de metadados da nuvem e nunca é um destino válido."
            )
        if _is_private(endereco):
            raise UnsafeUrlError(
                f"O host {host} aponta para um endereço de rede interna ({endereco}). "
                "Webhooks só podem sair para a internet."
            )


def _resolve(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolve o host. IP literal não consulta DNS — `getaddrinfo` devolve o próprio."""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"Não foi possível resolver o host {host}.") from exc
    enderecos = []
    for info in infos:
        bruto = info[4][0]
        try:
            enderecos.append(ipaddress.ip_address(bruto))
        except ValueError:  # pragma: no cover - getaddrinfo devolve IP
            continue
    if not enderecos:  # pragma: no cover - idem
        raise UnsafeUrlError(f"Não foi possível resolver o host {host}.")
    return enderecos


def _is_private(endereco: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        endereco.is_private
        or endereco.is_loopback
        or endereco.is_link_local
        or endereco.is_reserved
        or endereco.is_multicast
        or endereco.is_unspecified
    )
