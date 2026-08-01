class InvalidCredentialsError(Exception):
    pass


class InvalidRefreshTokenError(Exception):
    pass


class RateLimitExceededError(Exception):
    pass


class WeakPasswordError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("Senha não atende à política.")


class InvalidResetTokenError(Exception):
    pass
