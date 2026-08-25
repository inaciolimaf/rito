class FeatureDisabledError(Exception):
    """Regra 4: `is_enabled = false` → 409, com o motivo explícito."""


class UnknownFeatureError(Exception):
    """Chave fora do catálogo de `features.py` → 422."""
