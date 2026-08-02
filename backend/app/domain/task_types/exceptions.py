class TaskTypeNameAlreadyExistsError(Exception):
    """Regra 7: nome único por tenant, sem acento na comparação."""


class TaskTypeInUseError(Exception):
    """Regra 5: excluir tipo em uso exige transferência antes."""


class SystemTaskTypeError(Exception):
    """Regra 4: tarefa sistêmica não pode ser excluída nem renomeada."""


class StepNotFoundError(Exception):
    """`step_id`, quando informado, precisa existir no catálogo global de fases."""
