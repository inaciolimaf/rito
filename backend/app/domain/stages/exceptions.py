class StepNotFoundError(Exception):
    pass


class StageNameAlreadyExistsError(Exception):
    """Nome duplicado dentro da mesma fase (regra 6) — fases diferentes podem repetir nome
    (a fonte real do ADVBOX tem "PLANEJAMENTO" em Negociação e em Marketing)."""

    pass


class InvalidReorderError(Exception):
    """Algum id não existe no tenant, ou os ids não pertencem todos à mesma fase (regra 5:
    "ordenação é por position dentro da fase")."""

    pass


class SuggestedWorkflowNotFoundError(Exception):
    """Spec 053: `suggested_workflow_id` precisa apontar pra um workflow existente
    do tenant."""

    pass


class StageInUseError(Exception):
    """Regra 1 da spec 101: etapa referenciada por algum processo exige transferência
    antes de excluir. A dependência (`lawsuits.stage_id`, FK NOT NULL) existe desde a
    spec 022 — a guarda ficou como stub até aqui."""

    pass
