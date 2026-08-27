"""Redação de dado sensível no log (spec 097, regra 3).

O log é o lugar onde PII vaza sem ninguém decidir vazar: alguém loga o corpo da
requisição para depurar, o corpo tem CPF, e o CPF fica seis meses no coletor. A regra 3
inverte o ônus — o formatter mascara por padrão e quem quer o valor cru precisa não
logá-lo.

Duas frentes, porque o dado chega de duas formas:

- **por chave** (`{"password": "..."}`, `extra={"api_key": ...}`): o nome do campo diz
  que é segredo, independentemente do formato do valor;
- **por formato** (um CPF no meio de uma frase): o nome não diz nada, o formato diz tudo.

O que NÃO é varrido por formato são os campos estruturais que o próprio formatter monta
(`request_id`, `tenant_id`, `user_id`, `timestamp`...). São UUIDs e datas nossos, sem PII,
e varrê-los só criaria falso positivo: 1 em cada 100 UUIDs tem 11 dígitos seguidos em
algum lugar e viraria "CPF" mascarado.
"""

import re
from collections.abc import Mapping, Sequence
from typing import Any

MASK = "***"

# Nome de campo que denuncia segredo. Casa em qualquer posição do nome
# (`x_api_key`, `refresh_token`, `smtp_password`) — a chave é sempre nossa.
SENSITIVE_KEY_RE = re.compile(
    r"(?i)(senha|password|passwd|secret|token|api[_-]?key|apikey|authorization|"
    r"credential|chave|cpf|cnpj|email|e_mail|phone|telefone|celular)"
)

# `password=abc`, `token: xyz`, `api_key = 123` dentro de uma frase livre.
_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(senha|password|passwd|secret|token|api[_-]?key|apikey|authorization|chave)\b"
    r"(\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|\S+)"
)
_BEARER_RE = re.compile(r"(?i)\b(bearer|basic)\s+\S+")

# Delimitadores que impedem casar dígitos que moram dentro de um UUID ou de um
# identificador maior (`a1b2-12345678901`), onde não há PII nenhuma.
_EDGE = r"(?<![0-9A-Za-z_-])"
_EDGE_END = r"(?![0-9A-Za-z_-])"

_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # E-mail antes de tudo: o domínio tem pontos que confundiriam os padrões numéricos.
    re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    # CNPJ e CPF formatados.
    re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b"),
    re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"),
    # Telefone BR formatado, com ou sem DDI. As mesmas bordas dos padrões numéricos
    # abaixo: sem elas, os 11 primeiros dígitos de um UUID viram "telefone".
    re.compile(_EDGE + r"(?:\+55[\s.-]?)?\(?\d{2}\)?[\s.-]?\d{4,5}[\s.-]?\d{4}" + _EDGE_END),
    # CNPJ e CPF/celular só com dígitos — CNPJ (14) antes de CPF (11), senão o
    # padrão de 11 comeria o começo do de 14.
    re.compile(_EDGE + r"\d{14}" + _EDGE_END),
    re.compile(_EDGE + r"\d{10,11}" + _EDGE_END),
    # JWT: três blocos base64url separados por ponto.
    re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+"),
)


def redact_text(value: str) -> str:
    """Mascara segredo e PII em texto livre (mensagem de log, corpo de erro).

    `Bearer`/`Basic` vêm ANTES da atribuição: em `Authorization: Bearer abc`, o padrão
    de atribuição casaria `Authorization: Bearer` e deixaria o token — o valor da
    atribuição é o esquema, não a credencial.
    """
    value = _BEARER_RE.sub(lambda m: f"{m.group(1)} {MASK}", value)
    value = _ASSIGNMENT_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", value)
    for pattern in _VALUE_PATTERNS:
        value = pattern.sub(MASK, value)
    return value


def redact_value(value: Any, *, key: str | None = None) -> Any:  # noqa: ANN401
    """Mascara um valor de log, recursivamente.

    `Any` é inevitável: `logger.info(..., extra={...})` aceita qualquer coisa
    serializável, e é exatamente o payload arbitrário que precisa ser varrido.
    """
    if key is not None and SENSITIVE_KEY_RE.search(key):
        return MASK
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {str(k): redact_value(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [redact_value(item) for item in value]
    if isinstance(value, bytes):
        return MASK
    return value
