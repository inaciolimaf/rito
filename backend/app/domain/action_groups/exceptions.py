class ActionGroupNotFoundError(Exception):
    pass


class ActionGroupNameAlreadyExistsError(Exception):
    pass


class ActionGroupInUseError(Exception):
    """Regra 3: grupo com tipos de ação vinculados exige transferência antes de excluir."""

    pass


class LawsuitTypeNotFoundError(Exception):
    pass


class LawsuitTypeNameAlreadyExistsError(Exception):
    pass


class InvalidTransferError(Exception):
    """from_id/to_id iguais, ou algum dos dois não existe no tenant."""

    pass
