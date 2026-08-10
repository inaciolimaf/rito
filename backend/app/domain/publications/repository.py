from sqlalchemy import select

from app.core.repository import BaseRepository
from app.domain.publications.models import (
    Publication,
    PublicationLawyer,
    PublicationRecipient,
)


class PublicationRepository(BaseRepository[Publication]):
    model = Publication

    async def get_by_hash(self, hash_: str) -> Publication | None:
        result = await self.session.scalars(select(Publication).where(Publication.hash == hash_))
        return result.first()


class PublicationRecipientRepository(BaseRepository[PublicationRecipient]):
    model = PublicationRecipient


class PublicationLawyerRepository(BaseRepository[PublicationLawyer]):
    model = PublicationLawyer
