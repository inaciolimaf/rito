import re

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import get_settings

_SPECIAL_CHARS_PATTERN = re.compile(r"[^\w\s]")


def _hasher() -> PasswordHasher:
    settings = get_settings()
    return PasswordHasher(
        time_cost=settings.argon2_time_cost,
        memory_cost=settings.argon2_memory_cost,
        parallelism=settings.argon2_parallelism,
    )


def hash_password(password: str) -> str:
    return _hasher().hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _hasher().verify(password_hash, password)
    except VerifyMismatchError:
        return False
    return True


def validate_password_policy(password: str) -> list[str]:
    """Regra 1 da spec 004: mínimo 8, número, minúscula, maiúscula, especial."""
    errors = []
    if len(password) < 8:
        errors.append("Mínimo de 8 caracteres.")
    if not any(c.isdigit() for c in password):
        errors.append("Precisa de ao menos um número.")
    if not any(c.islower() for c in password):
        errors.append("Precisa de ao menos uma letra minúscula.")
    if not any(c.isupper() for c in password):
        errors.append("Precisa de ao menos uma letra maiúscula.")
    if not _SPECIAL_CHARS_PATTERN.search(password):
        errors.append("Precisa de ao menos um caractere especial.")
    return errors
