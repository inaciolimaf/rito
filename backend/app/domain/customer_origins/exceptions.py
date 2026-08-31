class CustomerOriginNameAlreadyExistsError(Exception):
    pass


class CustomerOriginInUseError(Exception):
    """Regra 3 da spec 101: origem referenciada por algum contato exige transferência
    antes de excluir. `customers.origin_id` existe desde a spec 017 — é a dívida nº 13."""

    pass
