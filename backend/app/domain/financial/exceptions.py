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


class BankAccountNameAlreadyExistsError(Exception):
    """Regra 8 (spec 055): nome único por tenant."""


class InstitutionNotFoundError(Exception):
    """`institution_id` precisa apontar pra uma instituição existente, quando informado."""


class DefaultAccountNeedsReplacementError(Exception):
    """Regra 7 (spec 055): inativar a conta padrão exige eleger outra antes."""


class TransactionCategoryNotFoundError(Exception):
    """`category_id` precisa apontar pra uma categoria existente do tenant."""


class TransactionCategoryTypeMismatchError(Exception):
    """Regra 1 (spec 056): RECEITA só aceita categoria de tipo RECEITA; DESPESA só de
    DESPESA — a regra que mais quebra integração."""

    def __init__(self, category_type: str) -> None:
        super().__init__(category_type)
        self.category_type = category_type


class TransactionCostCenterNotFoundError(Exception):
    """`cost_center_id` precisa apontar pra um centro de custo existente do tenant."""


class TransactionAccountNotFoundError(Exception):
    """`debit_account_id`/`credit_account_id` precisam apontar pra contas existentes."""


class TransactionCustomerNotFoundError(Exception):
    """`customer_id` precisa apontar pra um contato existente do tenant."""


class TransactionLawsuitNotFoundError(Exception):
    """`lawsuit_id` precisa apontar pra um processo existente do tenant."""


class PaidTransactionNotDeletableError(Exception):
    """Regra 10: excluir lançamento pago exige estornar antes."""


class SeriesHasPaidTransactionError(Exception):
    """Regra 8 (spec 057): excluir a série inteira (`scope=all`) com alguma parcela/
    ocorrência já paga exige estornar antes — mesmo espírito da regra 10 da 056."""
