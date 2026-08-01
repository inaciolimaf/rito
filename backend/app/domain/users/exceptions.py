class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidInvitationError(Exception):
    """Token de convite inexistente, expirado ou já aceito — mesma mensagem genérica dos
    tokens de reset de senha (spec 004): não dá pista de qual dos três é o caso."""

    pass


class CannotChangeOwnRoleError(Exception):
    pass


class LastActiveGestorError(Exception):
    pass


class OabRequiredError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
