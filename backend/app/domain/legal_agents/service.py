"""Produção de minuta por agente de petição (spec 087).

O agente não "sabe" o processo: ele coleta o que precisa por tool calling (regra 1,
sem RAG), monta a peça sobre a estrutura do modelo do escritório quando existe (regra
2) e devolve HTML para o editor da 065 (regra 3).

Duas garantias ficam do lado do CÓDIGO, não do prompt: citação sem respaldo no contexto
é removida (regra 6) e nada é salvo no processo sem o usuário mandar (regra 12).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.base import ToolContext
from app.ai.tools.runner import ToolRunner
from app.core.repository import BaseRepository
from app.domain.ai.service import AiRunner
from app.domain.legal_agents.citations import strip_unsupported_citations
from app.domain.legal_agents.models import AgentGeneration, LegalAgent
from app.domain.templates.models import Template, TemplateType
from app.domain.templates.repository import TemplateRepository
from app.domain.users.models import User
from app.integrations.openrouter.types import Message

FEATURE_KEY = "petition_draft"
CONTENT_FORMAT = "html"

# Regra 1: o contexto vem destas ferramentas, sempre — o agente não escolhe.
CONTEXT_TOOLS: tuple[tuple[str, str], ...] = (
    ("get_lawsuit", "lawsuit_id"),
    ("get_lawsuit_timeline", "lawsuit_id"),
)

_STRUCTURE_FROM_TEMPLATE = (
    "Use EXATAMENTE a estrutura do modelo do escritório abaixo: mantenha os títulos e a "
    "ordem das seções, e escreva o conteúdo de cada uma. Onde houver {{variavel}}, "
    "mantenha a variável como está — ela é preenchida depois pelo sistema.\n\n"
    "MODELO DO ESCRITÓRIO:\n{template}"
)

_STRUCTURE_DEFAULT = "Não há modelo do escritório para esta peça: monte a estrutura padrão da área."


class AgentNotFoundError(Exception):
    """Agente inexistente, de outro escritório ou desabilitado (regra 9) → 404."""


class GenerationNotFoundError(Exception):
    """Minuta inexistente → 404."""


@dataclass
class GenerationResult:
    generation: AgentGeneration
    tool_labels: list[str] = field(default_factory=list)


class LegalAgentRepository(BaseRepository[LegalAgent]):
    model = LegalAgent

    async def list_available(self, *, include_disabled: bool = False) -> Sequence[LegalAgent]:
        """O RLS já traz os de sistema (tenant nulo) e os do escritório."""
        stmt = select(LegalAgent).order_by(LegalAgent.practice_area, LegalAgent.code)
        if not include_disabled:
            stmt = stmt.where(LegalAgent.is_enabled.is_(True))
        return (await self.session.scalars(stmt)).all()

    async def get_enabled(self, agent_id: uuid.UUID) -> LegalAgent | None:
        stmt = select(LegalAgent).where(LegalAgent.id == agent_id, LegalAgent.is_enabled.is_(True))
        return (await self.session.scalars(stmt)).first()


class AgentGenerationRepository(BaseRepository[AgentGeneration]):
    model = AgentGeneration

    async def list_for_lawsuit(self, lawsuit_id: uuid.UUID) -> Sequence[AgentGeneration]:
        stmt = (
            select(AgentGeneration)
            .where(AgentGeneration.lawsuit_id == lawsuit_id)
            .order_by(AgentGeneration.created_at.desc())
        )
        return (await self.session.scalars(stmt)).all()


class LegalAgentService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID, runner: AiRunner) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.runner = runner
        self.agents = LegalAgentRepository(session)
        self.generations = AgentGenerationRepository(session)
        self.templates = TemplateRepository(session)

    async def generate(
        self,
        *,
        agent_id: uuid.UUID,
        lawsuit_id: uuid.UUID,
        user: User,
        instructions: str | None,
        template_id: uuid.UUID | None,
        thread_id: uuid.UUID | None = None,
    ) -> GenerationResult:
        agent = await self.agents.get_enabled(agent_id)
        if agent is None:
            raise AgentNotFoundError

        contexto, rotulos = await self._collect_context(lawsuit_id, user, thread_id)
        template = await self._resolve_template(agent, template_id)
        prompt = self._build_prompt(agent, contexto, template, instructions)

        response = await self.runner.run(
            feature_key=FEATURE_KEY,
            messages=[
                Message(role="system", content=agent.system_prompt),
                Message(role="user", content=prompt),
            ],
            user_id=user.id,
        )
        # Regra 6: o prompt pede; aqui é onde a regra é cumprida.
        html, removidas = strip_unsupported_citations(response.content or "", contexto)

        generation = AgentGeneration(
            tenant_id=self.tenant_id,
            agent_id=agent.id,
            lawsuit_id=lawsuit_id,
            thread_id=thread_id,
            user_instructions=instructions,
            content={"format": CONTENT_FORMAT, "html": html},
            template_used_id=template.id if template else None,
            model=response.model,
            tokens_used=response.usage.prompt_tokens + response.usage.completion_tokens,
            warnings=removidas,
            generated_by=user.id,
        )
        self.session.add(generation)
        await self.session.flush()
        return GenerationResult(generation=generation, tool_labels=rotulos)

    async def save_as_template(
        self, generation: AgentGeneration, *, user: User, name: str | None
    ) -> Template:
        """Regra 12: sair da IA e virar documento do escritório é decisão do usuário —
        é este endpoint, e só ele, que cruza essa linha."""
        conteudo = str((generation.content or {}).get("html", ""))
        template = Template(
            tenant_id=self.tenant_id,
            name=name or f"Minuta gerada por IA — {generation.created_at.date().isoformat()}",
            type=TemplateType.PETICAO,
            content=conteudo,
            created_by=user.id,
        )
        self.session.add(template)
        await self.session.flush()
        generation.saved_template_id = template.id
        await self.session.flush()
        return template

    async def update_prompt(
        self, agent: LegalAgent, *, system_prompt: str | None, restore: bool
    ) -> LegalAgent:
        """Regra 10: o escritório reescreve o prompt e pode voltar ao de fábrica.

        Editar um agente de SISTEMA cria uma cópia do escritório em vez de alterar o
        catálogo global — um tenant não reescreve o prompt do vizinho.
        """
        if restore:
            agent.system_prompt = agent.original_system_prompt
            await self.session.flush()
            return agent
        if system_prompt is None:
            return agent
        if agent.tenant_id is None:
            copia = LegalAgent(
                tenant_id=self.tenant_id,
                code=agent.code,
                name=agent.name,
                practice_area=agent.practice_area,
                system_prompt=system_prompt,
                original_system_prompt=agent.original_system_prompt,
                default_template_id=agent.default_template_id,
            )
            self.session.add(copia)
            await self.session.flush()
            return copia
        agent.system_prompt = system_prompt
        await self.session.flush()
        return agent

    # ------------------------------------------------------------------ interno

    async def _collect_context(
        self, lawsuit_id: uuid.UUID, user: User, thread_id: uuid.UUID | None
    ) -> tuple[str, list[str]]:
        """Regra 1: contexto por tool calling, com o RLS e o RBAC de quem pediu."""
        from app.domain.ai.copilot import TOOL_LABELS

        runner = ToolRunner(
            ToolContext(
                session=self.session,
                tenant_id=self.tenant_id,
                user=user,
                thread_id=thread_id,
            )
        )
        partes: list[str] = []
        rotulos: list[str] = []
        for tool_name, argumento in CONTEXT_TOOLS:
            resultado = await runner.call(tool_name, {argumento: str(lawsuit_id)})
            rotulos.append(TOOL_LABELS.get(tool_name, tool_name))
            partes.append(f"### {tool_name}\n{resultado}")
        return "\n\n".join(partes), rotulos

    async def _resolve_template(
        self, agent: LegalAgent, template_id: uuid.UUID | None
    ) -> Template | None:
        alvo = template_id or agent.default_template_id
        if alvo is None:
            return None
        return await self.templates.get_by_id(alvo)

    def _build_prompt(
        self,
        agent: LegalAgent,
        contexto: str,
        template: Template | None,
        instructions: str | None,
    ) -> str:
        estrutura = (
            _STRUCTURE_FROM_TEMPLATE.format(template=template.content)
            if template is not None
            else _STRUCTURE_DEFAULT
        )
        blocos = [
            "CONTEXTO DO PROCESSO (coletado agora, por consulta ao sistema):",
            contexto,
            "",
            estrutura,
        ]
        if instructions:
            # Regra 5: o que o advogado pediu vem por último e manda — menos nas regras
            # de segurança, que estão no prompt de sistema e não são negociáveis.
            blocos += [
                "",
                "INSTRUÇÕES DO ADVOGADO (têm precedência sobre as orientações gerais, "
                "exceto sobre as regras inegociáveis):",
                instructions,
            ]
        return "\n".join(blocos)


def context_text(generation: AgentGeneration) -> str:
    return str((generation.content or {}).get("html", ""))


__all__ = [
    "CONTEXT_TOOLS",
    "FEATURE_KEY",
    "AgentGeneration",
    "AgentGenerationRepository",
    "AgentNotFoundError",
    "GenerationNotFoundError",
    "GenerationResult",
    "LegalAgent",
    "LegalAgentRepository",
    "LegalAgentService",
    "context_text",
]
