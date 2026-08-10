class AccountNotFoundError(Exception):
    pass


class ResponsibleUserNotFoundError(Exception):
    """Spec 045: o responsável geral por publicações precisa ser um usuário do tenant."""
