"""Intimação → tarefa (spec 045): o elo entre a captura do DJEN (042/044) e o
trabalho do escritório.

`PublicationRoutingService.route` faz o casamento publicação↔processo (§5,
3 estratégias) e, havendo processo, o roteamento em cascata do responsável
(4 rotas) — depois cria a tarefa sistêmica "Intimações Judiciais". `link`
atende o vínculo manual (regra 7: dispara o mesmo roteamento) e `reprocess`
reexecuta o casamento sem duplicar a tarefa (regra 1). `handle_cancellation`
é chamada pela sincronização (044) quando uma publicação já roteada é anulada
pelo tribunal (regra 8).
"""

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.br_documents import strip_document_mask
from app.domain.account.repository import AccountRepository
from app.domain.action_groups.repository import ActionGroupRepository, LawsuitTypeRepository
from app.domain.inbox.sections import PUBLICATIONS_TASK_TYPE_NAME
from app.domain.lawsuits.models import Lawsuit
from app.domain.lawsuits.repository import LawsuitRepository
from app.domain.monitored_terms.models import TermKind
from app.domain.monitored_terms.repository import MonitoredTermRepository
from app.domain.notifications.dispatch import NotificationDispatcher
from app.domain.notifications.models import NotificationEvent
from app.domain.posts.models import Post
from app.domain.posts.repository import PostRepository
from app.domain.publications.exceptions import LawsuitNotFoundError, NoResponsibleAvailableError
from app.domain.publications.models import Publication
from app.domain.publications.repository import PublicationLawyerRepository, PublicationRepository
from app.domain.task_types.repository import TaskTypeRepository
from app.domain.users.repository import UserRepository
from app.integrations.messaging.base import MessagingChannel

_BODY_MAX_LENGTH = 5_000  # regra 5: comentário truncado, com link para o inteiro teor.
_CANCELLATION_COMMENT = (
    "⚠️ Publicação anulada pelo tribunal (motivo: {reason}). A tarefa não foi excluída "
    "— confirme com o advogado se ela ainda procede."
)


class PublicationRoutingService:
    def __init__(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        channels: Mapping[str, MessagingChannel] | None = None,
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.publications = PublicationRepository(session)
        self.lawyers = PublicationLawyerRepository(session)
        self.lawsuits = LawsuitRepository(session)
        self.action_groups = ActionGroupRepository(session)
        self.lawsuit_types = LawsuitTypeRepository(session)
        self.terms = MonitoredTermRepository(session)
        self.accounts = AccountRepository(session)
        self.users = UserRepository(session)
        self.task_types = TaskTypeRepository(session)
        self.posts = PostRepository(session)
        self.dispatcher = NotificationDispatcher(session, tenant_id, channels)

    async def route(self, publication: Publication) -> Publication:
        """Casamento automático — chamado ao registrar uma publicação nova (044)."""
        lawsuit, matched_by = await self._match(publication)
        return await self._apply(publication, lawsuit=lawsuit, matched_by=matched_by)

    async def link(self, publication: Publication, lawsuit_id: uuid.UUID) -> Publication:
        """Vínculo manual (regra 7): o usuário escolhe o processo — dispara o mesmo
        roteamento em cascata da rota automática."""
        lawsuit = await self.lawsuits.get_by_id(lawsuit_id)
        if lawsuit is None:
            raise LawsuitNotFoundError
        return await self._apply(publication, lawsuit=lawsuit, matched_by="manual")

    async def reprocess(self, publication: Publication) -> Publication:
        """Regra 1: reprocessar não duplica — se já existe tarefa, o casamento/roteamento
        não roda de novo."""
        if publication.post_id is not None:
            return publication
        return await self.route(publication)

    async def handle_cancellation(self, publication: Publication) -> None:
        """Regra 8: publicação anulada depois de já ter gerado tarefa — a tarefa recebe
        um alerta e vira urgente; nunca é excluída (quem decide é o advogado)."""
        if publication.post_id is None:
            return
        post = await self.posts.get_by_id(publication.post_id)
        if post is None:
            return
        post.is_urgent = True
        post.comments = self._append_comment(
            post.comments,
            _CANCELLATION_COMMENT.format(reason=publication.cancellation_reason or "não informado"),
        )
        await self.session.flush()

    @staticmethod
    def _append_comment(existing: str | None, note: str) -> str:
        return f"{existing}\n\n{note}" if existing else note

    async def _apply(
        self, publication: Publication, *, lawsuit: Lawsuit | None, matched_by: str | None
    ) -> Publication:
        publication.matched_by = matched_by
        publication.lawsuit_id = lawsuit.id if lawsuit is not None else None
        publication.processed_at = datetime.now(UTC)
        if lawsuit is None or publication.post_id is not None:
            # regra 6: sem processo casado não gera tarefa; regra 1: já tinha tarefa.
            await self.session.flush()
            return publication

        task_type = await self.task_types.get_by_name(PUBLICATIONS_TASK_TYPE_NAME)
        if task_type is None:
            # Tipo sistêmico ainda não seedado no tenant — fica vinculada, sem tarefa,
            # até a configuração ser corrigida (reprocessar tenta de novo).
            await self.session.flush()
            return publication

        user_id, routed_by = await self._route_responsible(lawsuit, publication)
        post = await self._create_task(
            lawsuit,
            publication,
            task_type_id=task_type.id,
            reward=task_type.reward,
            user_id=user_id,
        )
        publication.post_id = post.id
        publication.routed_to = user_id
        publication.routed_by = routed_by
        await self.session.flush()
        await self.dispatcher.dispatch(
            NotificationEvent.INTIMACAO,
            title="Nova intimação roteada",
            body=publication.body[:_BODY_MAX_LENGTH],
            link=f"/lawsuits/{lawsuit.id}",
        )
        return publication

    async def _match(self, publication: Publication) -> tuple[Lawsuit | None, str | None]:
        """§5, casamento — na ordem, para na primeira que resolve."""
        if publication.process_number:
            # regra 9: só dígitos; regra 4 da 042 já normaliza o lado da publicação.
            digits = strip_document_mask(publication.process_number)
            candidates = await self.lawsuits.find_by_process_number_digits(digits)
            if len(candidates) == 1:
                return candidates[0], "process_number"
            if len(candidates) > 1:
                return None, "ambiguous"  # regra 11

        term_user_id = await self._find_term_responsible(publication)
        if term_user_id is not None:
            candidates = await self.lawsuits.list_by_responsible(term_user_id)
            if len(candidates) == 1:
                return candidates[0], "lawyer_id"

        return None, None

    async def _find_term_responsible(self, publication: Publication) -> uuid.UUID | None:
        """Estratégia 2 / rota 2: o termo OAB monitorado cujo valor casa com algum
        advogado da publicação, restrito a termos com responsável configurado."""
        lawyers = await self.lawyers.list_for_publication(publication.id)
        for lawyer in lawyers:
            if not lawyer.oab_number or not lawyer.oab_state:
                continue
            term = await self.terms.find_duplicate(
                kind=TermKind.OAB,
                value=strip_document_mask(lawyer.oab_number),
                oab_state=lawyer.oab_state,
            )
            if term is not None and term.user_id is not None:
                return term.user_id
        return None

    async def _route_responsible(
        self, lawsuit: Lawsuit, publication: Publication
    ) -> tuple[uuid.UUID, str]:
        """§5, roteamento em cascata — para na primeira rota que resolve."""
        lawsuit_type = await self.lawsuit_types.get_by_id(lawsuit.lawsuit_type_id)
        if lawsuit_type is not None:
            group = await self.action_groups.get_by_id(lawsuit_type.action_group_id)
            if group is not None and group.publications_user_id is not None:
                return group.publications_user_id, "action_group"

        term_user_id = await self._find_term_responsible(publication)
        if term_user_id is not None:
            return term_user_id, "term_user"

        account = await self.accounts.get_current()
        if account is not None and account.default_publications_user_id is not None:
            return account.default_publications_user_id, "general"

        gestor = await self.users.get_oldest_active_gestor()
        if gestor is not None:
            return gestor.id, "gestor_fallback"

        raise NoResponsibleAvailableError

    async def _create_task(
        self,
        lawsuit: Lawsuit,
        publication: Publication,
        *,
        task_type_id: uuid.UUID,
        reward: int,
        user_id: uuid.UUID,
    ) -> Post:
        comments = publication.body[:_BODY_MAX_LENGTH]
        if publication.link:
            comments = f"{comments}\n\nInteiro teor: {publication.link}"
        post = Post(
            tenant_id=self.tenant_id,
            lawsuit_id=lawsuit.id,
            task_type_id=task_type_id,
            created_by=user_id,
            scheduled_date=publication.availability_date,  # regra 3
            reward_snapshot=reward,
            comments=comments,
        )
        return await self.posts.create_with_assignees(post, [user_id])
