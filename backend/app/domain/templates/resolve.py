import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.account.repository import AccountRepository
from app.domain.action_groups.repository import LawsuitTypeRepository
from app.domain.courts.models import Court
from app.domain.customers.models import MaritalStatus
from app.domain.customers.repository import CustomerRepository
from app.domain.lawsuits.repository import LawsuitRepository
from app.domain.stages.repository import StageRepository, StepRepository
from app.domain.templates.exceptions import TemplateNotFoundError
from app.domain.templates.repository import TemplateRepository
from app.domain.templates.variables import VariableScope, build_variable_map, resolve_content
from app.domain.users.models import Occupation, User


class CustomerScopeNotFoundError(Exception):
    pass


class LawsuitScopeNotFoundError(Exception):
    pass


@dataclass
class ResolvedTemplate:
    content: str
    header_content: str
    footer_content: str
    missing: list[str]


class TemplateResolverService:
    """Monta o `VariableScope` (spec 066) a partir dos ids recebidos e resolve os 3
    campos de texto do modelo (corpo, cabeçalho, rodapé) contra ele."""

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.templates = TemplateRepository(session)
        self.customers = CustomerRepository(session)
        self.lawsuits = LawsuitRepository(session)
        self.lawsuit_types = LawsuitTypeRepository(session)
        self.stages = StageRepository(session)
        self.steps = StepRepository(session)
        self.accounts = AccountRepository(session)

    async def _build_scope(
        self, *, customer_id: uuid.UUID | None, lawsuit_id: uuid.UUID | None, current_user: User
    ) -> VariableScope:
        customer = None
        marital_status_name = None
        if customer_id is not None:
            customer = await self.customers.get_by_id(customer_id)
            if customer is None:
                raise CustomerScopeNotFoundError
            if customer.marital_status_id is not None:
                marital_status = await self.session.get(MaritalStatus, customer.marital_status_id)
                marital_status_name = marital_status.name if marital_status else None

        lawsuit = None
        lawsuit_type_name = None
        lawsuit_court_name = None
        lawsuit_step_name = None
        lawsuit_responsible_name = None
        if lawsuit_id is not None:
            lawsuit = await self.lawsuits.get_by_id(lawsuit_id)
            if lawsuit is None:
                raise LawsuitScopeNotFoundError
            lawsuit_type = await self.lawsuit_types.get_by_id(lawsuit.lawsuit_type_id)
            lawsuit_type_name = lawsuit_type.name if lawsuit_type else None
            if lawsuit.court_id is not None:
                court = await self.session.get(Court, lawsuit.court_id)
                lawsuit_court_name = court.name if court else None
            stage = await self.stages.get_by_id(lawsuit.stage_id)
            if stage is not None:
                step = await self.steps.get_by_step_id(stage.step_id)
                lawsuit_step_name = step.name if step else None
            responsible = await self.session.get(User, lawsuit.user_id)
            lawsuit_responsible_name = responsible.name if responsible else None

        account = await self.accounts.get_current()

        user_occupation_name = None
        if current_user.occupation_id is not None:
            occupation = await self.session.get(Occupation, current_user.occupation_id)
            user_occupation_name = occupation.name if occupation else None

        return VariableScope(
            customer=customer,
            customer_marital_status_name=marital_status_name,
            lawsuit=lawsuit,
            lawsuit_type_name=lawsuit_type_name,
            lawsuit_court_name=lawsuit_court_name,
            lawsuit_step_name=lawsuit_step_name,
            lawsuit_responsible_name=lawsuit_responsible_name,
            account=account,
            user=current_user,
            user_occupation_name=user_occupation_name,
        )

    async def resolve(
        self,
        template_id: uuid.UUID,
        *,
        customer_id: uuid.UUID | None,
        lawsuit_id: uuid.UUID | None,
        current_user: User,
    ) -> ResolvedTemplate:
        template = await self.templates.get_by_id(template_id)
        if template is None:
            raise TemplateNotFoundError

        scope = await self._build_scope(
            customer_id=customer_id, lawsuit_id=lawsuit_id, current_user=current_user
        )
        variable_map = build_variable_map(scope)

        content, content_missing = resolve_content(template.content, variable_map)
        header, header_missing = resolve_content(template.header_content, variable_map)
        footer, footer_missing = resolve_content(template.footer_content, variable_map)

        missing = sorted(set(content_missing + header_missing + footer_missing))
        return ResolvedTemplate(
            content=content, header_content=header, footer_content=footer, missing=missing
        )
