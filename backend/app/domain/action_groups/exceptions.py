class ActionGroupNotFoundError(Exception):
    pass


class ActionGroupNameAlreadyExistsError(Exception):
    pass


class ActionGroupInUseError(Exception):
    """Regra 3: grupo com tipos de ação vinculados exige transferência antes de excluir."""

    pass


class LawsuitTypeNameAlreadyExistsError(Exception):
    pass
