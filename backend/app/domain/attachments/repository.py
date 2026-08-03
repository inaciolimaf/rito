import uuid
from collections.abc import Sequence

from sqlalchemy import delete as sql_delete
from sqlalchemy import select

from app.core.repository import BaseRepository
from app.domain.attachments.models import Attachment


class AttachmentRepository(BaseRepository[Attachment]):
    model = Attachment

    async def create(self, attachment: Attachment) -> Attachment:
        self.session.add(attachment)
        await self.session.flush()
        return attachment

    async def list_for(
        self, attached_to_type: str, attached_to_id: uuid.UUID
    ) -> Sequence[Attachment]:
        stmt = (
            select(Attachment)
            .where(
                Attachment.attached_to_type == attached_to_type,
                Attachment.attached_to_id == attached_to_id,
            )
            .order_by(Attachment.created_at)
        )
        return (await self.session.scalars(stmt)).all()

    async def delete_for(self, attached_to_type: str, attached_to_id: uuid.UUID) -> list[str]:
        """Remove TODOS os anexos de um alvo e devolve as storage_keys — o service
        apaga os objetos do storage em seguida (regra 9: excluir comentário remove
        os anexos dele)."""
        rows = await self.list_for(attached_to_type, attached_to_id)
        await self.session.execute(
            sql_delete(Attachment).where(
                Attachment.attached_to_type == attached_to_type,
                Attachment.attached_to_id == attached_to_id,
            )
        )
        return [row.storage_key for row in rows]
