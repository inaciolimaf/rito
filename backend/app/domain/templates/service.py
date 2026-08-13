import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import decode_cursor, encode_cursor
from app.domain.templates.exceptions import TemplateNotFoundError
from app.domain.templates.models import Template, TemplateType
from app.domain.templates.repository import TemplateRepository


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

    async def create(
        self, user_id: uuid.UUID, *, name: str, type_: TemplateType, content: str
    ) -> Template:
        return await self.templates.create(
            Template(
                tenant_id=self.tenant_id,
                name=name,
                type=type_,
                content=content,
                created_by=user_id,
            )
        )

    async def update(
        self, template_id: uuid.UUID, *, name: str, type_: TemplateType, content: str
    ) -> Template:
        template = await self.get(template_id)
        template.name = name
        template.type = type_
        template.content = content
        template.updated_at = datetime.now(UTC)
        return template

    async def move_to_trash(self, template_id: uuid.UUID) -> None:
        """Regra 3: lixeira reversível — nunca apaga a linha."""
        template = await self.get(template_id)
        template.deleted_at = datetime.now(UTC)

    async def restore(self, template_id: uuid.UUID) -> Template:
        template = await self.get(template_id)
        template.deleted_at = None
        template.updated_at = datetime.now(UTC)
        return template

    async def duplicate(self, template_id: uuid.UUID, user_id: uuid.UUID) -> Template:
        """Regra 6: cópia sempre ativa (nunca herda `deleted_at` do original)."""
        original = await self.get(template_id)
        return await self.templates.create(
            Template(
                tenant_id=self.tenant_id,
                name=f"{original.name} (cópia)",
                type=original.type,
                content=original.content,
                created_by=user_id,
            )
        )
