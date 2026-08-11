import contextlib
import uuid
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.attachments.models import Attachment
from app.domain.attachments.repository import AttachmentRepository
from app.domain.attachments.rules import validate_attachment
from app.domain.comments.models import PostComment
from app.domain.financial.repository import TransactionRepository
from app.domain.posts.models import Post
from app.domain.posts.repository import PostRepository
from app.domain.posts.visibility import is_involved
from app.domain.users.models import User, UserRole
from app.integrations.storage.base import FileStorage

_DOWNLOAD_URL_EXPIRY_SECONDS = 5 * 60  # regra 6: URL assinada válida por 5 min

# ADMINISTRADOR ou acima remove anexo alheio (mesma régua da conclusão por terceiro).
_ADMIN_OR_ABOVE = {UserRole.ADMINISTRADOR, UserRole.GESTOR}

# Tipos de alvo suportados — 'customer' chega com spec própria; 'transaction' desde a
# spec 058 (financeiro).
_KNOWN_TARGET_TYPES = {"post", "comment", "transaction"}

# Regra 7 (spec 058): no máximo 20 anexos por lançamento — só vale pra esse alvo, não
# existe limite equivalente hoje pra post/comment.
_MAX_TRANSACTION_ATTACHMENTS = 20


class TransactionAttachmentLimitError(Exception):
    """Regra 7 (spec 058): 21º anexo num lançamento → 422."""


class AttachmentTargetNotFoundError(Exception):
    """Alvo inexistente, de tipo desconhecido ou sem acesso (regra 7) — tudo 404:
    para quem não tem acesso, o alvo simplesmente não existe."""


class AttachmentNotFoundError(Exception):
    pass


class AttachmentDeleteForbiddenError(Exception):
    """Só quem enviou (ou ADMINISTRADOR+) pode remover o anexo."""


class AttachmentResponse(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    attached_to_type: str
    attached_to_id: uuid.UUID
    uploaded_by: uuid.UUID
    created_at: datetime


class AttachmentService:
    def __init__(self, session: AsyncSession, storage: FileStorage, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.storage = storage
        self.tenant_id = tenant_id
        self.attachments = AttachmentRepository(session)
        self.posts = PostRepository(session)
        self.transactions = TransactionRepository(session)

    async def _post_for_target(
        self, attached_to_type: str, attached_to_id: uuid.UUID
    ) -> Post | None:
        """O post por trás do alvo — a regra 7 (visibilidade da tarefa privada) vale
        para anexo em comentário via o post do comentário."""
        if attached_to_type == "post":
            return await self.posts.get_by_id(attached_to_id)
        if attached_to_type == "comment":
            comment = await self.session.get(PostComment, attached_to_id)
            if comment is None or comment.deleted_at is not None:
                return None
            return await self.posts.get_by_id(comment.post_id)
        return None

    async def _validate_target(
        self, attached_to_type: str, attached_to_id: uuid.UUID, user: User
    ) -> None:
        """Confirma que o alvo existe e é acessível. Lançamentos (spec 058) não têm
        regra de visibilidade própria de anexo — quem chega até aqui já passou pelo
        `require_financial` do endpoint; só falta confirmar que o id existe no tenant
        (RLS garante que não vaza de outro)."""
        if attached_to_type not in _KNOWN_TARGET_TYPES:
            raise AttachmentTargetNotFoundError
        if attached_to_type == "transaction":
            if await self.transactions.get_by_id(attached_to_id) is None:
                raise AttachmentTargetNotFoundError
            return
        post = await self._post_for_target(attached_to_type, attached_to_id)
        if post is None:
            raise AttachmentTargetNotFoundError
        if post.is_private and not is_involved(
            post, await self.posts.assignee_ids_for(post.id), user.id
        ):
            # Regra 7 (spec 035): anexo de tarefa privada segue a mesma restrição — 404, não 403.
            raise AttachmentTargetNotFoundError

    async def upload(
        self,
        user: User,
        *,
        attached_to_type: str,
        attached_to_id: uuid.UUID,
        filename: str,
        content_type: str,
        content: bytes,
    ) -> Attachment:
        # Regra 5: tamanho e tipo antes de qualquer IO de storage.
        validate_attachment(filename=filename, content_type=content_type, size_bytes=len(content))
        await self._validate_target(attached_to_type, attached_to_id, user)
        if attached_to_type == "transaction":
            # Regra 7 (spec 058): no máximo 20 anexos por lançamento.
            existing = await self.attachments.list_for(attached_to_type, attached_to_id)
            if len(existing) >= _MAX_TRANSACTION_ATTACHMENTS:
                raise TransactionAttachmentLimitError
        storage_key = f"{self.tenant_id}/attachments/{uuid.uuid4()}"
        await self.storage.upload(key=storage_key, content=content, content_type=content_type)
        return await self.attachments.create(
            Attachment(
                tenant_id=self.tenant_id,
                storage_key=storage_key,
                filename=filename,
                content_type=content_type,
                size_bytes=len(content),
                attached_to_type=attached_to_type,
                attached_to_id=attached_to_id,
                uploaded_by=user.id,
            )
        )

    async def _get_accessible(self, attachment_id: uuid.UUID, user: User) -> Attachment:
        attachment = await self.attachments.get_by_id(attachment_id)
        if attachment is None:
            raise AttachmentNotFoundError
        try:
            await self._validate_target(
                attachment.attached_to_type, attachment.attached_to_id, user
            )
        except AttachmentTargetNotFoundError as exc:
            raise AttachmentNotFoundError from exc
        return attachment

    async def download_url(self, attachment_id: uuid.UUID, user: User) -> str:
        attachment = await self._get_accessible(attachment_id, user)
        # Regra 6: URL assinada com validade de 5 minutos.
        return self.storage.signed_url(
            attachment.storage_key, expires_in_seconds=_DOWNLOAD_URL_EXPIRY_SECONDS
        )

    async def delete(self, attachment_id: uuid.UUID, user: User) -> None:
        attachment = await self._get_accessible(attachment_id, user)
        if attachment.uploaded_by != user.id and user.role not in _ADMIN_OR_ABOVE:
            raise AttachmentDeleteForbiddenError
        await self.session.delete(attachment)
        await self.session.flush()
        await self._delete_storage_object(attachment.storage_key)

    async def remove_all_for_comment(self, comment_id: uuid.UUID) -> None:
        """Regra 9 (spec 035): excluir o comentário remove os anexos dele (linhas + objetos)."""
        await self.remove_all_for("comment", comment_id)

    async def remove_all_for(self, attached_to_type: str, attached_to_id: uuid.UUID) -> None:
        """Regra 8 (spec 058): excluir o lançamento remove os anexos dele — mesmo
        padrão de `remove_all_for_comment` (spec 035), generalizado pelo alvo."""
        for storage_key in await self.attachments.delete_for(attached_to_type, attached_to_id):
            await self._delete_storage_object(storage_key)

    async def list_for(
        self, attached_to_type: str, attached_to_id: uuid.UUID, user: User
    ) -> list[Attachment]:
        await self._validate_target(attached_to_type, attached_to_id, user)
        return list(await self.attachments.list_for(attached_to_type, attached_to_id))

    async def _delete_storage_object(self, storage_key: str) -> None:
        """Best-effort: o objeto órfão no bucket é menos pior que falhar a exclusão
        da linha por um erro de storage."""
        with contextlib.suppress(Exception):
            await self.storage.delete(key=storage_key)
