class DocumentScopeNotFoundError(Exception):
    """Escopo (contato/processo) inexistente ou de outro tenant — regra 1: 404."""


class DocumentFolderNotFoundError(Exception):
    pass


class DocumentNotFoundError(Exception):
    pass


class DuplicateFolderNameError(Exception):
    """Regra 3: nome de pasta duplicado no mesmo nível do mesmo escopo — 409."""


class FolderScopeMismatchError(Exception):
    """Pasta pai pertence a outro escopo — nunca deveria acontecer pela API pública,
    mas o service confirma antes de aninhar (defesa em profundidade)."""
