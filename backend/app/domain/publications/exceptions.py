class PublicationAlreadyExistsError(Exception):
    """Regra 2: `hash` do DJEN é a chave de deduplicação — UNIQUE (tenant_id, hash)."""


class PublicationNotFoundError(Exception):
    """Publicação inexistente ou fora do tenant (RLS) — 404."""


class LawsuitNotFoundError(Exception):
    """Spec 045: vínculo manual exige um processo existente no tenant — 422."""


class NoResponsibleAvailableError(Exception):
    """Rota 4 esgotada: nenhum GESTOR ativo no tenant — não deveria acontecer (regra 8
    da spec 005 impede inativar o último), mas o roteamento falha explicitamente em
    vez de criar uma tarefa sem responsável."""
