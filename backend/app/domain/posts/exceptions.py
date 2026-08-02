import uuid


class LawsuitNotFoundError(Exception):
    """Regra 1: o processo é obrigatório e precisa existir no tenant."""


class TaskTypeNotFoundError(Exception):
    """Regra 1: o tipo de tarefa é obrigatório e precisa existir no tenant."""


class AssigneeNotActiveError(Exception):
    """Regra 9: todo responsável precisa ser um usuário ativo do tenant."""


class SquadNotFoundError(Exception):
    """O time informado precisa existir no tenant."""


class DuplicatePostError(Exception):
    """Regra 4: mesmo processo + tipo + data + mesmo conjunto de responsáveis é
    duplicata — 409 com o id existente."""

    def __init__(self, existing_id: uuid.UUID) -> None:
        super().__init__(str(existing_id))
        self.existing_id = existing_id
