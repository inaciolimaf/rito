class TermAlreadyExistsError(Exception):
    """Regra 3: mesmo (kind, value, oab_state) no tenant → 409."""


class SyncAlreadyRunningError(Exception):
    """Regra 10: sync manual com execução em andamento → 409."""


class InvalidTermStateError(Exception):
    """Transição de status inválida (ex.: pausar quem já está pausado)."""


class BackfillTooOldError(Exception):
    """Regra 6: captura inicial limitada a 12 meses.

    Vinha de um `model_validator` do Pydantic, que roda sem contexto de requisição e por
    isso só sabia perguntar a data ao servidor (spec 114). Desceu para o service, que é
    onde o `CLAUDE.md` §5 manda regra de negócio morar e onde o fuso do escritório chega.
    """
