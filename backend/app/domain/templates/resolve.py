import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.account.repository import AccountRepository
from app.domain.action_groups.repository import LawsuitTypeRepository
from app.domain.courts.models import Court
from app.domain.customers.models import Customer, MaritalStatus
from app.domain.customers.repository import CustomerRepository
from app.domain.lawsuits.models import Lawsuit
from app.domain.lawsuits.repository import LawsuitRepository
from app.domain.stages.repository import StageRepository, StepRepository
from app.domain.templates.exceptions import TemplateNotFoundError
from app.domain.templates.repository import TemplateRepository
from app.domain.templates.variables import VariableScope, build_variable_map, resolve_content
from app.domain.users.models import Occupation, User


@dataclass(frozen=True)
class _EscopoDoProcesso:
    """Os dados do processo que um modelo pode citar. Tudo opcional: sem processo no
    escopo, o documento simplesmente não tem essas variáveis."""

    lawsuit: Lawsuit | None = None
    type_name: str | None = None
    court_name: str | None = None
    step_name: str | None = None
    responsible_name: str | None = None


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
        customer, marital_status_name = await self._dados_do_contato(customer_id)
        processo = await self._dados_do_processo(lawsuit_id)
        return VariableScope(
            customer=customer,
            customer_marital_status_name=marital_status_name,
            lawsuit=processo.lawsuit,
            lawsuit_type_name=processo.type_name,
            lawsuit_court_name=processo.court_name,
            lawsuit_step_name=processo.step_name,
            lawsuit_responsible_name=processo.responsible_name,
            account=await self.accounts.get_current(),
            user=current_user,
            user_occupation_name=await self._nome_da_ocupacao(current_user),
        )

    async def _dados_do_contato(
        self, customer_id: uuid.UUID | None
    ) -> tuple[Customer | None, str | None]:
        """O contato e o nome do estado civil — que mora em outra tabela."""
        if customer_id is None:
            return None, None
        customer = await self.customers.get_by_id(customer_id)
        if customer is None:
            raise CustomerScopeNotFoundError
        if customer.marital_status_id is None:
            return customer, None
        marital_status = await self.session.get(MaritalStatus, customer.marital_status_id)
        return customer, (marital_status.name if marital_status else None)

    async def _dados_do_processo(self, lawsuit_id: uuid.UUID | None) -> "_EscopoDoProcesso":
        """O processo e os quatro nomes desnormalizados que o documento cita.

        Todos são «pode não existir»: tribunal é opcional no cadastro, e etapa, tipo e
        responsável podem ter sido apagados depois. Documento com lacuna é melhor que
        geração que estoura.
        """
        if lawsuit_id is None:
            return _EscopoDoProcesso()
        lawsuit = await self.lawsuits.get_by_id(lawsuit_id)
        if lawsuit is None:
            raise LawsuitScopeNotFoundError
        lawsuit_type = await self.lawsuit_types.get_by_id(lawsuit.lawsuit_type_id)
        court = (
            await self.session.get(Court, lawsuit.court_id)
            if lawsuit.court_id is not None
            else None
        )
        stage = await self.stages.get_by_id(lawsuit.stage_id)
        step = await self.steps.get_by_step_id(stage.step_id) if stage is not None else None
        responsible = await self.session.get(User, lawsuit.user_id)
        return _EscopoDoProcesso(
            lawsuit=lawsuit,
            type_name=lawsuit_type.name if lawsuit_type else None,
            court_name=court.name if court else None,
            step_name=step.name if step else None,
            responsible_name=responsible.name if responsible else None,
        )

    async def _nome_da_ocupacao(self, current_user: User) -> str | None:
        if current_user.occupation_id is None:
            return None
        occupation = await self.session.get(Occupation, current_user.occupation_id)
        return occupation.name if occupation else None

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
