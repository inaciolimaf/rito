class TermAlreadyExistsError(Exception):
    """Regra 3: mesmo (kind, value, oab_state) no tenant → 409."""


class SyncAlreadyRunningError(Exception):
    """Regra 10: sync manual com execução em andamento → 409."""


class InvalidTermStateError(Exception):
    """Transição de status inválida (ex.: pausar quem já está pausado)."""
