from datetime import datetime


class LawsuitTypeNotFoundError(Exception):
    """Regra 1: tipo de ação é obrigatório e precisa existir no tenant."""


class StageNotFoundError(Exception):
    """Regra 1: etapa é obrigatória e precisa existir no tenant."""


class ResponsibleNotActiveError(Exception):
    """Regra 9: responsável precisa ser um usuário ativo do tenant."""


class CourtSystemIncompatibleError(Exception):
    """Regra 8: sistema processual precisa pertencer ao tribunal escolhido."""


class PartyCustomerNotFoundError(Exception):
    """Spec 023: a parte precisa ser um contato existente do tenant."""


class DuplicatePartyError(Exception):
    """Regra 2 (spec 023): mesma pessoa no mesmo polo duas vezes é proibido —
    em polos distintos é permitido."""


class LastPartyError(Exception):
    """Regra 1 (spec 023): processo precisa de no mínimo 1 parte —
    remover a última é proibido."""


class TribunalMovementImmutableError(Exception):
    """Regra 3 (spec 026): movimentação com origin=TRIBUNAL é imutável pela UI."""


class MovementNotAuthorError(Exception):
    """Regra 4 (spec 026): movimentação manual só é editável/excluível por quem criou
    ou por ADMINISTRADOR."""


class FolderNotFoundError(Exception):
    """Spec 029: renomear uma pasta sem nenhum processo é 404."""


class FolderMergeNotConfirmedError(Exception):
    """Regra 4 (spec 029): renomear para uma pasta existente funde as duas — sem
    `merge: true` no payload, é 409 e a UI pede confirmação explícita."""

    def __init__(self, target: str) -> None:
        super().__init__(target)
        self.target = target


class NotResponsibleForLawsuitError(Exception):
    """Regra 10 (spec 051): Colaborador só move processo onde é o responsável;
    ADMINISTRADOR/GESTOR movem qualquer um."""


class LawsuitNotFoundError(Exception):
    """Regra 9 (spec 051): ação em massa é transacional — um id inexistente no lote
    (de outro tenant ou apagado) derruba a operação inteira, nenhuma mudança parcial."""


class WorkflowAlreadyAppliedError(Exception):
    """Regra 8 (spec 053): reaplicar exige confirmação explícita, mostrando quando a
    última aplicação aconteceu."""

    def __init__(self, applied_at: datetime) -> None:
        super().__init__(applied_at)
        self.applied_at = applied_at


class WorkflowApplicationNotFoundError(Exception):
    """Spec 053: id de aplicação inexistente (de outro tenant/processo, ou já
    desfeita) — 404 no desfazer."""


class WorkflowUndoWindowExpiredError(Exception):
    """Regra 5 (spec 053): desfazer só é possível em até 1 h da aplicação."""


class WorkflowUndoHasCompletedTaskError(Exception):
    """Regra 5 (spec 053): nenhuma das tarefas geradas pode ter sido concluída."""
