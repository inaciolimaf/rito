class CustomerOriginNameAlreadyExistsError(Exception):
    pass


class InvalidTransferError(Exception):
    """from_id/to_id iguais, ou algum dos dois não existe no tenant."""

    pass
