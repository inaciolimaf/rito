class PublicationAlreadyExistsError(Exception):
    """Regra 2: `hash` do DJEN é a chave de deduplicação — UNIQUE (tenant_id, hash)."""
