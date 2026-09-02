import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.br_documents import strip_document_mask
from app.core.repository import decode_cursor, encode_cursor
from app.domain.automations.engine import AutomationEngine
from app.domain.automations.models import TriggerKind
from app.domain.publications.exceptions import PublicationAlreadyExistsError
from app.domain.publications.export import build_pdf, build_xlsx
from app.domain.publications.models import (
    Publication,
    PublicationLawyer,
    PublicationRead,
    PublicationRecipient,
)
from app.domain.publications.repository import (
    PublicationCounts,
    PublicationFilterParams,
    PublicationLawyerRepository,
    PublicationReadRepository,
    PublicationRecipientRepository,
    PublicationRepository,
)
from app.domain.publications.schemas import PublicationFilters, PublicationListRow
from app.domain.users.repository import UserRepository
from app.integrations.djen.parser import ParsedCommunication

_EXPORT_ROW_CAP = 50_000  # regra 9


@dataclass
class PublicationDetail:
    publication: Publication
    recipients: list[PublicationRecipient]
    lawyers: list[PublicationLawyer]
    is_read: bool


def _resolve_interval(filters: PublicationFilters, today: date) -> tuple[date | None, date | None]:
    """Regra 1: padrão "últimos 7 dias" — `custom` usa as datas informadas.

    `today` é o do escritório (spec 114): "últimos 7 dias" contado do dia do servidor
    devolvia uma janela deslocada para quem não estivesse no fuso dele.
    """
    if filters.interval == "custom":
        return filters.date_from, filters.date_to
    days = {"today": 1, "3d": 3, "7d": 7}[filters.interval]
    return today - timedelta(days=days - 1), today


def _to_filter_params(
    filters: PublicationFilters, *, current_user_id: uuid.UUID, today: date
) -> PublicationFilterParams:
    date_from, date_to = _resolve_interval(filters, today)
    process_number_digits = (
        strip_document_mask(filters.process_number) if filters.process_number else None
    )
    return PublicationFilterParams(
        availability_from=date_from,
        availability_to=date_to,
        routed_to=filters.user_id,
        customer_id=filters.customer_id,
        court_code=filters.court_code,
        process_number_digits=process_number_digits,
        linked=filters.linked,
        cancelled=filters.cancelled,
        read=filters.read,
        current_user_id=current_user_id if filters.read is not None else None,
    )


def _publication_from(parsed: ParsedCommunication, tenant_id: uuid.UUID) -> Publication:
    """A intimação como ela chega do DJEN — cópia campo a campo, sem regra.

    Vinte e cinco atribuições sem decisão nenhuma no meio: extraídas de `register` na spec
    121 porque elas empurravam a função para 63 linhas e escondiam o que ela de fato faz —
    recusar duplicata, gravar, e desdobrar destinatários e advogados.
    """
    return Publication(
        tenant_id=tenant_id,
        external_id=parsed.external_id,
        hash=parsed.hash,
        availability_date=parsed.availability_date,
        court_code=parsed.court_code,
        communication_type=parsed.communication_type,
        document_type=parsed.document_type,
        organ_name=parsed.organ_name,
        organ_id=parsed.organ_id,
        body=parsed.body,
        process_number=parsed.process_number,
        medium=parsed.medium,
        medium_full=parsed.medium_full,
        class_name=parsed.class_name,
        class_code=parsed.class_code,
        communication_number=parsed.communication_number,
        link=parsed.link,
        status=parsed.status,
        is_active=parsed.is_active,
        cancellation_reason=parsed.cancellation_reason,
        cancelled_at=parsed.cancelled_at,
        raw_payload=parsed.raw_payload,
    )


class PublicationService:
    """Registro de publicações capturadas (spec 042) + listagem/leitura da tela de
    intimações (spec 048). A sincronização em lote é da spec 044."""

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.repository = PublicationRepository(session)
        self.recipients = PublicationRecipientRepository(session)
        self.lawyers = PublicationLawyerRepository(session)
        self.reads = PublicationReadRepository(session)
        self.users = UserRepository(session)

    def _add_parties(self, publication: Publication, parsed: ParsedCommunication) -> None:
        """Destinatários e advogados da intimação, como o DJEN os mandou.

        Sem `flush` aqui: as duas listas entram na mesma unidade de trabalho da publicação,
        e gravar a intimação sem as partes seria um estado que o resto do sistema não sabe
        interpretar.
        """
        for recipient in parsed.recipients:
            self.session.add(
                PublicationRecipient(
                    tenant_id=self.tenant_id,
                    publication_id=publication.id,
                    name=recipient.name,
                    pole=recipient.pole,
                )
            )
        for lawyer in parsed.lawyers:
            self.session.add(
                PublicationLawyer(
                    tenant_id=self.tenant_id,
                    publication_id=publication.id,
                    external_lawyer_id=lawyer.external_lawyer_id,
                    name=lawyer.name,
                    oab_number=lawyer.oab_number,
                    oab_state=lawyer.oab_state,
                )
            )

    async def _emit_received(self, publication: Publication) -> None:
        """Spec 092: intimação recebida é gatilho.

        «Chegou intimação nesse processo, avise o responsável» é a automação que todo
        escritório escreve primeiro — e por isso o evento sai daqui, do único caminho por
        onde uma intimação entra, e não do worker que por acaso a trouxe.
        """
        await AutomationEngine(self.session, self.tenant_id).emit(
            TriggerKind.PUBLICATION_RECEIVED.value,
            payload={
                "publication_id": str(publication.id),
                "process_number": publication.process_number,
                "court_code": publication.court_code,
                "communication_type": publication.communication_type,
            },
            subject_type="publication",
            subject_id=publication.id,
        )

    async def register(self, parsed: ParsedCommunication) -> Publication:
        if await self.repository.get_by_hash(parsed.hash) is not None:
            raise PublicationAlreadyExistsError

        publication = _publication_from(parsed, self.tenant_id)
        await self.repository.create(publication)
        self._add_parties(publication, parsed)
        await self.session.flush()
        await self._emit_received(publication)
        return publication

    async def get_by_id(self, publication_id: uuid.UUID) -> Publication | None:
        return await self.repository.get_by_id(publication_id)

    async def _rows_for(
        self, items: list[Publication], *, current_user_id: uuid.UUID
    ) -> list[PublicationListRow]:
        ids = [item.id for item in items]
        parties_by_pub = await self.recipients.names_for_many(ids)
        read_ids = await self.reads.read_publication_ids(current_user_id, ids)
        routed_ids = {item.routed_to for item in items if item.routed_to is not None}
        names = await self.users.names_for(routed_ids)
        return [
            PublicationListRow(
                publication=item,
                parties=parties_by_pub.get(item.id, []),
                routed_to_name=names.get(item.routed_to) if item.routed_to else None,
                is_read=item.id in read_ids,
            )
            for item in items
        ]

    async def list_publications(
        self,
        *,
        filters: PublicationFilters,
        current_user_id: uuid.UUID,
        cursor: str | None,
        limit: int,
        today: date,
    ) -> tuple[list[PublicationListRow], str | None, int]:
        params = _to_filter_params(filters, current_user_id=current_user_id, today=today)
        decoded = None
        if cursor:
            raw_value, cursor_id = decode_cursor(cursor)
            decoded = (date.fromisoformat(raw_value), cursor_id)

        items, total = await self.repository.list_filtered(
            filters=params, cursor=decoded, limit=limit
        )
        rows = await self._rows_for(list(items), current_user_id=current_user_id)

        next_cursor = None
        if len(items) == limit:
            last = items[-1]
            next_cursor = encode_cursor(last.availability_date.isoformat(), last.id)
        return rows, next_cursor, total

    async def get_counts(
        self, *, filters: PublicationFilters, current_user_id: uuid.UUID, today: date
    ) -> PublicationCounts:
        params = _to_filter_params(filters, current_user_id=current_user_id, today=today)
        return await self.repository.counts(filters=params, current_user_id=current_user_id)

    async def get_detail(
        self, publication: Publication, *, current_user_id: uuid.UUID
    ) -> PublicationDetail:
        recipients = await self.recipients.list_for_publication(publication.id)
        lawyers = await self.lawyers.list_for_publication(publication.id)
        is_read = await self.reads.get_for(publication.id, current_user_id) is not None
        return PublicationDetail(
            publication=publication,
            recipients=list(recipients),
            lawyers=list(lawyers),
            is_read=is_read,
        )

    async def mark_read(self, publication: Publication, user_id: uuid.UUID) -> PublicationRead:
        """Regra 5: leitura é POR USUÁRIO — o que um leu não marca para os outros."""
        existing = await self.reads.get_for(publication.id, user_id)
        if existing is not None:
            return existing
        read = PublicationRead(
            tenant_id=self.tenant_id, publication_id=publication.id, user_id=user_id
        )
        return await self.reads.create(read)

    async def export(
        self,
        *,
        format_: Literal["xlsx", "pdf"],
        filters: PublicationFilters,
        current_user_id: uuid.UUID,
        today: date,
    ) -> bytes:
        # Regra 9: respeita os filtros ativos; teto de 50.000 linhas.
        params = _to_filter_params(filters, current_user_id=current_user_id, today=today)
        items, _total = await self.repository.list_filtered(
            filters=params, cursor=None, limit=_EXPORT_ROW_CAP
        )
        rows = await self._rows_for(list(items), current_user_id=current_user_id)
        return build_xlsx(rows) if format_ == "xlsx" else build_pdf(rows)
