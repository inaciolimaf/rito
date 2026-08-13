import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.documents.models import Document, DocumentScopeType
from app.domain.documents.service import DocumentService
from app.domain.templates.exceptions import TemplateNotFoundError
from app.domain.templates.pdf import render_pdf
from app.domain.templates.resolve import TemplateResolverService
from app.domain.users.models import User
from app.integrations.messaging.document_email import DocumentMailer
from app.integrations.storage.base import FileStorage


class DocumentSaveFailedError(Exception):
    """Regra 6: `upload_many` (spec 063) recusou o PDF (quota/tipo/tamanho) — o
    chamador HTTP decide o status code a partir do `reason`."""

    def __init__(self, reason: str) -> None:
        self.reason = reason


class TemplateGenerationService:
    """Compõe resolução de variáveis (spec 066) + render de PDF + as 3 saídas
    (baixar/enviar/salvar) — cada uma reaproveita o mesmo PDF, gerado uma vez por
    chamada (regra 1)."""

    def __init__(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        storage: FileStorage,
        mailer: DocumentMailer,
    ) -> None:
        self.resolver = TemplateResolverService(session, tenant_id)
        self.documents = DocumentService(session=session, storage=storage, tenant_id=tenant_id)
        self.mailer = mailer

    async def _generate(
        self,
        template_id: uuid.UUID,
        *,
        customer_id: uuid.UUID | None,
        lawsuit_id: uuid.UUID | None,
        current_user: User,
    ) -> tuple[str, bytes]:
        template = await self.resolver.templates.get_by_id(template_id)
        if template is None:
            raise TemplateNotFoundError
        resolved = await self.resolver.resolve(
            template_id, customer_id=customer_id, lawsuit_id=lawsuit_id, current_user=current_user
        )
        pdf_bytes = render_pdf(
            header_content=resolved.header_content,
            content=resolved.content,
            footer_content=resolved.footer_content,
            watermark_text=template.watermark_text,
        )
        # Regra 3: nome previsível, sem timestamp/sufixo.
        return f"{template.name}.pdf", pdf_bytes

    async def generate_pdf(
        self,
        template_id: uuid.UUID,
        *,
        customer_id: uuid.UUID | None,
        lawsuit_id: uuid.UUID | None,
        current_user: User,
    ) -> tuple[str, bytes]:
        return await self._generate(
            template_id, customer_id=customer_id, lawsuit_id=lawsuit_id, current_user=current_user
        )

    async def save_to_cloud(
        self,
        template_id: uuid.UUID,
        *,
        customer_id: uuid.UUID | None,
        lawsuit_id: uuid.UUID,
        current_user: User,
    ) -> Document:
        filename, pdf_bytes = await self._generate(
            template_id, customer_id=customer_id, lawsuit_id=lawsuit_id, current_user=current_user
        )
        results = await self.documents.upload_many(
            current_user,
            scope_type=DocumentScopeType.LAWSUIT,
            scope_id=lawsuit_id,
            folder_id=None,
            files=[(filename, "application/pdf", pdf_bytes)],
        )
        result = results[0]
        if result.document is None:
            raise DocumentSaveFailedError(result.error or "Falha ao salvar na nuvem.")
        return result.document

    async def send_email(
        self,
        template_id: uuid.UUID,
        *,
        customer_id: uuid.UUID | None,
        lawsuit_id: uuid.UUID | None,
        to: str,
        subject: str | None,
        current_user: User,
    ) -> None:
        filename, pdf_bytes = await self._generate(
            template_id, customer_id=customer_id, lawsuit_id=lawsuit_id, current_user=current_user
        )
        await self.mailer.send(
            to=to,
            subject=subject or filename,
            body=f"Segue em anexo {filename}.",
            filename=filename,
            content=pdf_bytes,
        )
