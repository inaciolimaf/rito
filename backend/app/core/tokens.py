import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.config import get_settings

_JWT_ALGORITHM = "HS256"


def create_access_token(*, user_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.secret_key, algorithms=[_JWT_ALGORITHM])


def hash_token(raw_token: str) -> str:
    """Hash rápido (SHA-256) para tokens opacos de alta entropia.

    Diferente de senha: o token já tem ~256 bits de aleatoriedade própria
    (`secrets.token_urlsafe`), então não precisa de Argon2 — só precisamos de
    uma busca determinística por hash, o que Argon2 (com salt por hash) não permite.
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_refresh_token() -> tuple[str, str]:
    """Retorna (token bruto para o cliente, hash para guardar no banco)."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)
