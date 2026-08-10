import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.publications.exceptions import PublicationAlreadyExistsError
from app.domain.publications.models import (
    Publication,
    PublicationLawyer,
    PublicationRecipient,
)
from app.domain.publications.repository import PublicationRepository
from app.integrations.djen.parser import ParsedCommunication


class PublicationService:
    """Registro de publicações capturadas (spec 042). A sincronização em lote é
    da spec 044 — aqui a unidade de trabalho é uma comunicação já parseada."""

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.repository = PublicationRepository(session)

    async def register(self, parsed: ParsedCommunication) -> Publication:
        if await self.repository.get_by_hash(parsed.hash) is not None:
            raise PublicationAlreadyExistsError

        publication = Publication(
            tenant_id=self.tenant_id,
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
        await self.repository.create(publication)
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
        await self.session.flush()
        return publication
