"""Log estruturado (spec 097, regras 1, 3, 9, 10 e 12).

Um log só serve para investigar incidente se der para **filtrar** por ele. Por isso
todo registro sai em JSON com os campos de correlação da regra 1 — e por isso o
formatter passa tudo pela redação da regra 3 antes de escrever: quem loga não deveria
precisar lembrar que aquele dicionário tem um CPF dentro.

Só há um handler, `StreamHandler` para stdout (regra 12): quem coleta é o orquestrador
(regra 13 da 099). Handler de arquivo ou de rede faria I/O síncrono dentro do caminho
quente da requisição.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from app.core.observability.context import (
    request_id_var,
    route_var,
    tenant_id_var,
    user_id_var,
)
from app.core.observability.redaction import redact_value

# Campos que o `logging` põe no LogRecord por conta própria — o que sobrar depois de
# tirá-los é o `extra=` que o chamador passou, e é isso que vai para o payload.
_RESERVED_RECORD_FIELDS = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}

# Campos montados pelo formatter: são nossos (UUID, data, nome de rota), nunca têm PII,
# e varrê-los pela redação só produziria falso positivo (ver docstring de redaction.py).
_TRUSTED_FIELDS = frozenset(
    {
        "timestamp",
        "level",
        "logger",
        "request_id",
        "tenant_id",
        "user_id",
        "route",
        "duration_ms",
        "status",
        "method",
        "trace_id",
    }
)


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Any: payload de log é JSON arbitrário por natureza (mistura str/None/exception
        # formatada); um TypedDict engessaria toda chamada de logger.info(extra=...).
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_value(record.getMessage()),
            "request_id": request_id_var.get(),
            "tenant_id": tenant_id_var.get(),
            "user_id": user_id_var.get(),
            "route": route_var.get(),
            "duration_ms": None,
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED_RECORD_FIELDS:
                continue
            payload[key] = value if key in _TRUSTED_FIELDS else redact_value(value, key=key)
        # Regra 9: stack trace é do log de ERRO. O log de requisição bem-sucedida não
        # carrega exceção nenhuma — é uma linha por request, e stack ali seria ruído
        # que ninguém lê e byte que todo mundo paga.
        if record.exc_info:
            payload["exception"] = redact_value(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Regra 10: o nível vem de `LOG_LEVEL` — trocar de INFO para DEBUG não é deploy."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
