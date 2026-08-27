"""Assinatura do webhook (spec 093, regra 2).

HMAC-SHA256 sobre `timestamp.corpo` — o timestamp entra no que é assinado, e não só num
header ao lado, porque assinar apenas o corpo permitiria reenviar a mesma mensagem
válida para sempre. Quem recebe confere a assinatura E a janela.
"""

import hashlib
import hmac
import secrets

SIGNATURE_HEADER = "X-Rito-Signature"
TIMESTAMP_HEADER = "X-Rito-Timestamp"
EVENT_HEADER = "X-Rito-Event"
DELIVERY_HEADER = "X-Rito-Delivery"

# Janela sugerida a quem recebe. Não é imposta aqui — quem valida é o outro lado.
REPLAY_WINDOW_SECONDS = 300


def generate_secret() -> str:
    """Segredo do endpoint (regra 8): gerado pelo sistema, mostrado uma vez."""
    return f"whsec_{secrets.token_urlsafe(32)}"


def sign(*, secret: str, body: bytes, timestamp: int) -> str:
    mensagem = f"{timestamp}.".encode() + body
    assinatura = hmac.new(secret.encode("utf-8"), mensagem, hashlib.sha256).hexdigest()
    return f"sha256={assinatura}"


def verify(*, secret: str, body: bytes, timestamp: int, signature: str) -> bool:
    """Publicado junto do produto: é o que a documentação manda o cliente implementar.

    `compare_digest` e não `==` — comparação de string vaza o tamanho do prefixo comum
    pelo tempo, e assinatura conferida com `==` é assinatura conferida pela metade.
    """
    return hmac.compare_digest(sign(secret=secret, body=body, timestamp=timestamp), signature)
