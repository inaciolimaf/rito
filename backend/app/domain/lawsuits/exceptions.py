class LawsuitTypeNotFoundError(Exception):
    """Regra 1: tipo de ação é obrigatório e precisa existir no tenant."""


class StageNotFoundError(Exception):
    """Regra 1: etapa é obrigatória e precisa existir no tenant."""


class ResponsibleNotActiveError(Exception):
    """Regra 9: responsável precisa ser um usuário ativo do tenant."""


class CourtSystemIncompatibleError(Exception):
    """Regra 8: sistema processual precisa pertencer ao tribunal escolhido."""
