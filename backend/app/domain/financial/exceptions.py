class DreGroupNotFoundError(Exception):
    """Regra: `dre_group_id` precisa apontar pra um dos 10 grupos existentes."""


class FinancialCategoryNameAlreadyExistsError(Exception):
    """Regra 5: nome único por tenant, sem acento na comparação."""


class DefaultCategoryNotDeletableError(Exception):
    """Regra 3: categoria semeada (`is_default`) não pode ser excluída, só inativada."""


class CostCenterNameAlreadyExistsError(Exception):
    """Regra 5: nome único por tenant, sem acento na comparação."""


class DefaultCostCenterNotDeletableError(Exception):
    """Regra 8: o centro de custo `GERAL` (semeado) nunca é excluível."""
