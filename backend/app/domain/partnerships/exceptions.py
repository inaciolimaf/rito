class PartnershipAlreadyExistsError(Exception):
    """Regra 1: já existe convite/parceria para o mesmo e-mail neste escritório → 409."""


class InvalidInviteError(Exception):
    """Token inexistente, já usado, para outro e-mail ou do próprio escritório → 400."""


class PartnershipNotFoundError(Exception):
    """Parceria inexistente (ou de outro escritório, o que dá no mesmo) → 404."""


class LawsuitNotSharedError(Exception):
    """O processo não está compartilhado com o escritório da sessão → 404."""


class SharingForbiddenError(Exception):
    """Regra 5: parceiro sem `can_create_tasks` tentando criar tarefa → 403."""


class InvalidTaskTypeError(Exception):
    """Tipo de tarefa fora do catálogo do escritório dono → 422."""
