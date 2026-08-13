import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import decode_cursor, encode_cursor
from app.domain.templates.exceptions import PublicTemplateNotFoundError, TemplateNotFoundError
from app.domain.templates.models import PublicTemplate, Template, TemplateType
from app.domain.templates.repository import PublicTemplateRepository, TemplateRepository
from app.domain.templates.schemas import TemplateCreateRequest, TemplateUpdateRequest


class TemplateService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.templates = TemplateRepository(session)

    async def list_templates(
        self, *, view: str, query: str | None, cursor: str | None, limit: int
    ) -> tuple[list[Template], str | None, int]:
        decoded_cursor = decode_cursor(cursor) if cursor else None
        parsed_cursor = (
            (datetime.fromisoformat(decoded_cursor[0]), decoded_cursor[1])
            if decoded_cursor
            else None
        )
        items, total = await self.templates.list_filtered(
            view=view, query=query, cursor=parsed_cursor, limit=limit
        )
        next_cursor = None
        if len(items) == limit:
            last = items[-1]
            next_cursor = encode_cursor(last.created_at.isoformat(), last.id)
        return list(items), next_cursor, total

    async def get(self, template_id: uuid.UUID) -> Template:
        template = await self.templates.get_by_id(template_id)
        if template is None:
            raise TemplateNotFoundError
        return template

    async def create(self, user_id: uuid.UUID, data: TemplateCreateRequest) -> Template:
        return await self.templates.create(
            Template(
                tenant_id=self.tenant_id,
                name=data.name,
                type=data.type,
                content=data.content,
                header_content=data.header_content,
                footer_content=data.footer_content,
                watermark_text=data.watermark_text,
                created_by=user_id,
            )
        )

    async def update(self, template_id: uuid.UUID, data: TemplateUpdateRequest) -> Template:
        template = await self.get(template_id)
        template.name = data.name
        template.type = data.type
        template.content = data.content
        template.header_content = data.header_content
        template.footer_content = data.footer_content
        template.watermark_text = data.watermark_text
        template.updated_at = datetime.now(UTC)
        return template

    async def move_to_trash(self, template_id: uuid.UUID) -> None:
        """Regra 3 (spec 064): lixeira reversível — nunca apaga a linha."""
        template = await self.get(template_id)
        template.deleted_at = datetime.now(UTC)

    async def restore(self, template_id: uuid.UUID) -> Template:
        template = await self.get(template_id)
        template.deleted_at = None
        template.updated_at = datetime.now(UTC)
        return template

    async def duplicate(self, template_id: uuid.UUID, user_id: uuid.UUID) -> Template:
        """Regra 6 (spec 064): cópia sempre ativa (nunca herda `deleted_at` do
        original) — leva cabeçalho/rodapé/marca d'água junto (regra 065 §1: fazem
        parte do documento, não só o corpo)."""
        original = await self.get(template_id)
        return await self.templates.create(
            Template(
                tenant_id=self.tenant_id,
                name=f"{original.name} (cópia)",
                type=original.type,
                content=original.content,
                header_content=original.header_content,
                footer_content=original.footer_content,
                watermark_text=original.watermark_text,
                created_by=user_id,
            )
        )


class PublicTemplateService:
    """Biblioteca pública (spec 068) — leitura do catálogo global e "copiar" pro
    tenant atual."""

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.tenant_id = tenant_id
        self.public_templates = PublicTemplateRepository(session)
        self.templates = TemplateRepository(session)

    async def list_templates(self, *, type_: TemplateType | None) -> list[PublicTemplate]:
        return list(await self.public_templates.list_filtered(type_=type_))

    async def copy(self, public_template_id: uuid.UUID, user_id: uuid.UUID) -> Template:
        """Regra 2/4: cria um `Template` comum do tenant, editável dali em diante,
        com o mesmo nome do original (sem sufixo — é a primeira cópia, não uma
        duplicata de algo que o tenant já tem, spec 064 regra 6)."""
        original = await self.public_templates.get_by_id(public_template_id)
        if original is None:
            raise PublicTemplateNotFoundError
        return await self.templates.create(
            Template(
                tenant_id=self.tenant_id,
                name=original.name,
                type=original.type,
                content=original.content,
                header_content=original.header_content,
                footer_content=original.footer_content,
                watermark_text=original.watermark_text,
                created_by=user_id,
            )
        )
