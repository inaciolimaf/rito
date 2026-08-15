import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.image_processing import extension_for, process_image
from app.domain.account.exceptions import AccountNotFoundError, ResponsibleUserNotFoundError
from app.domain.account.models import Account, AccountPlan
from app.domain.account.repository import AccountRepository
from app.domain.account.schemas import AccountUpdateRequest
from app.domain.users.models import User
from app.integrations.storage.base import FileStorage


class AccountService:
    def __init__(self, session: AsyncSession, storage: FileStorage, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.storage = storage
        self.tenant_id = tenant_id
        self.accounts = AccountRepository(session)

    async def get(self) -> Account | None:
        return await self.accounts.get_current()

    async def upsert(self, data: AccountUpdateRequest) -> Account:
        """PUT faz criar-ou-atualizar — a spec não define um endpoint de criação
        separado (nenhuma spec de onboarding/provisionamento de tenant existe ainda)."""
        account = await self.accounts.get_current()
        fields = data.model_dump()

        if account is None:
            account = Account(tenant_id=self.tenant_id, **fields)
            return await self.accounts.create(account)

        for field, value in fields.items():
            setattr(account, field, value)
        return account

    async def upload_logo(self, content: bytes, content_type: str) -> Account:
        account = await self.accounts.get_current()
        if account is None:
            raise AccountNotFoundError

        processed = process_image(content, content_type)
        key = f"logos/{self.tenant_id}/{uuid.uuid4()}.{extension_for(content_type)}"
        await self.storage.upload(key=key, content=processed, content_type=content_type)

        account.logo_key = key
        account.updated_at = datetime.now(UTC)
        return account

    async def update_publications_settings(self, user_id: uuid.UUID | None) -> Account:
        account = await self.accounts.get_current()
        if account is None:
            raise AccountNotFoundError
        if user_id is not None and await self.session.get(User, user_id) is None:
            raise ResponsibleUserNotFoundError
        account.default_publications_user_id = user_id
        account.updated_at = datetime.now(UTC)
        return account

    async def update_access_tracking(self, enabled: bool) -> Account:
        """Spec 073, regra 11: desligar não apaga o histórico — só para de coletar."""
        account = await self.accounts.get_current()
        if account is None:
            raise AccountNotFoundError
        account.track_access_logs = enabled
        account.updated_at = datetime.now(UTC)
        return account

    async def update_plan(self, plan: AccountPlan) -> Account:
        """Regra 12 (spec 063): troca de plano não mexe em documento já enviado, só
        no teto de novos uploads — por isso não há nada além de gravar o valor."""
        account = await self.accounts.get_current()
        if account is None:
            raise AccountNotFoundError
        account.plan = plan
        account.updated_at = datetime.now(UTC)
        return account
