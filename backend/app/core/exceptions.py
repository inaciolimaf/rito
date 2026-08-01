class InvalidTransferError(Exception):
    """from_id/to_id iguais, ou algum dos dois não existe no tenant.

    Compartilhada entre os fluxos de "transferir antes de excluir" (customer_origins,
    action_groups/lawsuit_types, stages) — spec 020, pente-fino de duplicação.
    """
