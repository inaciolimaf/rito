import contextlib
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.account.models import AccountPlan
from app.domain.account.repository import AccountRepository
from app.domain.attachments.rules import (
    AttachmentTooLargeError,
    AttachmentTypeBlockedError,
    validate_attachment,
)
from app.domain.customers.repository import CustomerRepository
from app.domain.documents.exceptions import (
    DocumentFolderNotFoundError,
    DocumentNotFoundError,
    DocumentScopeNotFoundError,
    DuplicateFolderNameError,
    FolderScopeMismatchError,
)
from app.domain.documents.models import Document, DocumentFolder, DocumentScopeType
from app.domain.documents.quota import StorageQuotaExceededError, quota_bytes
from app.domain.documents.repository import DocumentFolderRepository, DocumentRepository
from app.domain.documents.schemas import SortField, SortOrder
from app.domain.lawsuits.repository import LawsuitRepository
from app.domain.users.models import User
from app.integrations.storage.base import FileStorage

_DOWNLOAD_URL_EXPIRY_SECONDS = 10 * 60  # regra 7: 10 min (mais generoso que anexo, spec 035)


class UploadResult:
    def __init__(
        self, *, filename: str, document: Document | None = None, error: str | None = None
    ) -> None:
        self.filename = filename
        self.document = document
        self.error = error

    @property
    def status(self) -> str:
        return "uploaded" if self.document is not None else "error"


class DocumentService:
    def __init__(self, session: AsyncSession, storage: FileStorage, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.storage = storage
        self.tenant_id = tenant_id
        self.folders = DocumentFolderRepository(session)
        self.documents = DocumentRepository(session)
        self.customers = CustomerRepository(session)
        self.lawsuits = LawsuitRepository(session)
        self.accounts = AccountRepository(session)

    async def _assert_scope_exists(
        self, scope_type: DocumentScopeType, scope_id: uuid.UUID
    ) -> None:
        exists = (
            await self.customers.get_by_id(scope_id) is not None
            if scope_type == DocumentScopeType.CUSTOMER
            else await self.lawsuits.get_by_id(scope_id) is not None
        )
        if not exists:
            raise DocumentScopeNotFoundError

    async def _plan(self) -> AccountPlan:
        account = await self.accounts.get_current()
        return account.plan if account is not None else AccountPlan.ESSENCIAL

    async def storage_usage(self) -> tuple[int, int, AccountPlan]:
        plan = await self._plan()
        used = await self.documents.total_size_bytes()
        return used, quota_bytes(plan), plan

    async def _assert_folder_in_scope(
        self, folder_id: uuid.UUID | None, *, scope_type: DocumentScopeType, scope_id: uuid.UUID
    ) -> DocumentFolder | None:
        if folder_id is None:
            return None
        folder = await self.folders.get_by_id(folder_id)
        if folder is None:
            raise DocumentFolderNotFoundError
        if folder.scope_type != scope_type or folder.scope_id != scope_id:
            raise FolderScopeMismatchError
        return folder

    async def create_folder(
        self,
        user: User,
        *,
        scope_type: DocumentScopeType,
        scope_id: uuid.UUID,
        parent_folder_id: uuid.UUID | None,
        name: str,
    ) -> DocumentFolder:
        await self._assert_scope_exists(scope_type, scope_id)
        await self._assert_folder_in_scope(
            parent_folder_id, scope_type=scope_type, scope_id=scope_id
        )
        existing = await self.folders.get_by_name(
            scope_type=scope_type, scope_id=scope_id, parent_folder_id=parent_folder_id, name=name
        )
        if existing is not None:
            raise DuplicateFolderNameError
        return await self.folders.create(
            DocumentFolder(
                tenant_id=self.tenant_id,
                scope_type=scope_type,
                scope_id=scope_id,
                parent_folder_id=parent_folder_id,
                name=name,
                created_by=user.id,
            )
        )

    async def delete_folder(self, folder_id: uuid.UUID) -> None:
        folder = await self.folders.get_by_id(folder_id)
        if folder is None:
            raise DocumentFolderNotFoundError
        # Regra 4: junta a subárvore inteira, apaga os objetos do storage e só então
        # a linha raiz — o ON DELETE CASCADE do banco cuida das subpastas/documentos
        # nas linhas, mas nunca do objeto no bucket.
        folder_ids = await self.folders.descendant_ids(folder_id)
        documents = await self.documents.list_in_folders(folder_ids)
        for document in documents:
            await self._delete_storage_object(document.storage_key)
        await self.folders.delete(folder)

    async def list_contents(
        self,
        *,
        scope_type: DocumentScopeType,
        scope_id: uuid.UUID,
        folder_id: uuid.UUID | None,
        sort: SortField,
        order: SortOrder,
    ) -> tuple[list[DocumentFolder], list[Document]]:
        await self._assert_scope_exists(scope_type, scope_id)
        await self._assert_folder_in_scope(folder_id, scope_type=scope_type, scope_id=scope_id)
        folders = await self.folders.list_in(
            scope_type=scope_type, scope_id=scope_id, parent_folder_id=folder_id
        )
        documents = await self.documents.list_in(
            scope_type=scope_type, scope_id=scope_id, folder_id=folder_id, sort=sort, order=order
        )
        return list(folders), list(documents)

    async def search(
        self, *, scope_type: DocumentScopeType, scope_id: uuid.UUID, query: str
    ) -> list[Document]:
        await self._assert_scope_exists(scope_type, scope_id)
        return list(
            await self.documents.search(scope_type=scope_type, scope_id=scope_id, query=query)
        )

    async def upload_many(
        self,
        user: User,
        *,
        scope_type: DocumentScopeType,
        scope_id: uuid.UUID,
        folder_id: uuid.UUID | None,
        files: list[tuple[str, str, bytes]],
    ) -> list[UploadResult]:
        """Regra 2: cada arquivo é independente — a falha de um nunca impede os
        outros. Regra 5: quota é conferida arquivo a arquivo, contra o total já
        confirmado (inclusive os já aceitos nesta mesma chamada)."""
        await self._assert_scope_exists(scope_type, scope_id)
        await self._assert_folder_in_scope(folder_id, scope_type=scope_type, scope_id=scope_id)

        used, quota, _plan = await self.storage_usage()
        results: list[UploadResult] = []
        for filename, content_type, content in files:
            try:
                validate_attachment(
                    filename=filename, content_type=content_type, size_bytes=len(content)
                )
                if used + len(content) > quota:
                    raise StorageQuotaExceededError
            except AttachmentTooLargeError:
                results.append(UploadResult(filename=filename, error="Arquivo acima de 50 MB."))
                continue
            except AttachmentTypeBlockedError:
                results.append(
                    UploadResult(filename=filename, error="Tipo de arquivo não permitido.")
                )
                continue
            except StorageQuotaExceededError:
                results.append(
                    UploadResult(
                        filename=filename, error="Quota de armazenamento do plano excedida."
                    )
                )
                continue

            storage_key = f"{self.tenant_id}/documents/{uuid.uuid4()}"
            await self.storage.upload(key=storage_key, content=content, content_type=content_type)
            document = await self.documents.create(
                Document(
                    tenant_id=self.tenant_id,
                    scope_type=scope_type,
                    scope_id=scope_id,
                    folder_id=folder_id,
                    storage_key=storage_key,
                    filename=filename,
                    content_type=content_type,
                    size_bytes=len(content),
                    uploaded_by=user.id,
                )
            )
            used += len(content)
            results.append(UploadResult(filename=filename, document=document))
        return results

    async def download_url(self, document_id: uuid.UUID) -> str:
        document = await self.documents.get_by_id(document_id)
        if document is None:
            raise DocumentNotFoundError
        return self.storage.signed_url(
            document.storage_key, expires_in_seconds=_DOWNLOAD_URL_EXPIRY_SECONDS
        )

    async def delete_document(self, document_id: uuid.UUID) -> None:
        document = await self.documents.get_by_id(document_id)
        if document is None:
            raise DocumentNotFoundError
        await self.documents.delete(document)
        await self._delete_storage_object(document.storage_key)

    async def _delete_storage_object(self, storage_key: str) -> None:
        """Best-effort, mesmo padrão de `AttachmentService`: objeto órfão no bucket é
        menos pior que falhar a exclusão da linha por um erro de storage."""
        with contextlib.suppress(Exception):
            await self.storage.delete(key=storage_key)
