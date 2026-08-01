class StepNotFoundError(Exception):
    pass


class StageNameAlreadyExistsError(Exception):
    """Nome duplicado dentro da mesma fase (regra 6) — fases diferentes podem repetir nome
    (a fonte real do ADVBOX tem "PLANEJAMENTO" em Negociação e em Marketing)."""

    pass


class InvalidTransferError(Exception):
    """from_id/to_id iguais, ou algum dos dois não existe no tenant."""

    pass


class InvalidReorderError(Exception):
    """Algum id não existe no tenant, ou os ids não pertencem todos à mesma fase (regra 5:
    "ordenação é por position dentro da fase")."""

    pass
