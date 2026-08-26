"""Rotas dos agentes de petição (spec 087 §5)."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http import get_or_404
from app.core.permissions import UserRole, require_role
from app.domain.ai.exceptions import FeatureDisabledError
from app.domain.ai.router import get_llm_provider
from app.domain.ai.service import AiRunner
from app.domain.auth.deps import get_session_for_current_user
from app.domain.legal_agents.models import AgentGeneration, LegalAgent
from app.domain.legal_agents.service import AgentNotFoundError, LegalAgentService
from app.domain.users.models import User
from app.integrations.openrouter.types import LLMError, LLMNotConfiguredError, LLMProvider

agents_router = APIRouter(prefix="/legal-agents", tags=["legal-agents"])
generations_router = APIRouter(prefix="/agent-generations", tags=["legal-agents"])

_AGENT_NOT_FOUND = "Agente não encontrado ou desabilitado."
_GENERATION_NOT_FOUND = "Minuta não encontrada."


class AgentResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    practice_area: str
    system_prompt: str
    is_customized: bool
    default_template_id: uuid.UUID | None
    is_enabled: bool


class AgentListResponse(BaseModel):
    items: list[AgentResponse]
    total: int


class GenerateRequest(BaseModel):
    lawsuit_id: uuid.UUID
    instructions: str | None = Field(default=None, max_length=4000)
    template_id: uuid.UUID | None = None


class GenerationResponse(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    lawsuit_id: uuid.UUID
    thread_id: uuid.UUID | None
    user_instructions: str | None
    content: dict[str, Any]
    template_used_id: uuid.UUID | None
    model: str
    tokens_used: int | None
    # Regra 6: o que a IA tentou citar sem respaldo e foi removido.
    warnings: list[dict[str, Any]]
    saved_template_id: uuid.UUID | None
    # Regra 8: o que o agente consultou para escrever.
    tool_labels: list[str] = Field(default_factory=list)
    created_at: datetime


class UpdateAgentRequest(BaseModel):
    system_prompt: str | None = Field(default=None, max_length=8000)
    restore_original: bool = False


class SaveAsTemplateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=200)


class SavedTemplateResponse(BaseModel):
    template_id: uuid.UUID
    generation_id: uuid.UUID


def _to_agent(agent: LegalAgent) -> AgentResponse:
    return AgentResponse(
        id=agent.id,
        code=agent.code,
        name=agent.name,
        practice_area=agent.practice_area,
        system_prompt=agent.system_prompt,
        # O escritório reescreveu (ou tem cópia própria) deste agente.
        is_customized=agent.tenant_id is not None,
        default_template_id=agent.default_template_id,
        is_enabled=agent.is_enabled,
    )


def _to_generation(
    generation: AgentGeneration, tool_labels: list[str] | None = None
) -> GenerationResponse:
    return GenerationResponse(
        id=generation.id,
        agent_id=generation.agent_id,
        lawsuit_id=generation.lawsuit_id,
        thread_id=generation.thread_id,
        user_instructions=generation.user_instructions,
        content=generation.content,
        template_used_id=generation.template_used_id,
        model=generation.model,
        tokens_used=generation.tokens_used,
        warnings=generation.warnings or [],
        saved_template_id=generation.saved_template_id,
        tool_labels=tool_labels or [],
        created_at=generation.created_at,
    )


def _service(session: AsyncSession, user: User, provider: LLMProvider) -> LegalAgentService:
    return LegalAgentService(
        session=session,
        tenant_id=user.tenant_id,
        runner=AiRunner(session, user.tenant_id, provider),
    )


@agents_router.get("")
async def list_agents(
    include_disabled: bool = Query(default=False),
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> AgentListResponse:
    """Regra 9: agente desabilitado não aparece no seletor."""
    service = _service(session, current_user, provider)
    rows = list(await service.agents.list_available(include_disabled=include_disabled))
    # Cópia do escritório tem precedência sobre o agente de sistema de mesmo código.
    por_codigo: dict[str, LegalAgent] = {}
    for agent in rows:
        atual = por_codigo.get(agent.code)
        if atual is None or (atual.tenant_id is None and agent.tenant_id is not None):
            por_codigo[agent.code] = agent
    items = sorted(por_codigo.values(), key=lambda item: (item.practice_area, item.code))
    return AgentListResponse(items=[_to_agent(item) for item in items], total=len(items))


@agents_router.put("/{agent_id}")
async def update_agent(
    agent_id: uuid.UUID,
    payload: UpdateAgentRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> AgentResponse:
    """Regra 10: o prompt é editável pelo GESTOR, e o de fábrica fica guardado."""
    service = _service(session, current_user, provider)
    agent = await get_or_404(lambda: service.agents.get_by_id(agent_id), _AGENT_NOT_FOUND)
    atualizado = await service.update_prompt(
        agent, system_prompt=payload.system_prompt, restore=payload.restore_original
    )
    return _to_agent(atualizado)


@agents_router.post("/{agent_id}/generate")
async def generate_brief(
    agent_id: uuid.UUID,
    payload: GenerateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> GenerationResponse:
    service = _service(session, current_user, provider)
    try:
        result = await service.generate(
            agent_id=agent_id,
            lawsuit_id=payload.lawsuit_id,
            user=current_user,
            instructions=payload.instructions,
            template_id=payload.template_id,
        )
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_AGENT_NOT_FOUND) from exc
    except (LLMNotConfiguredError, FeatureDisabledError) as exc:
        raise HTTPException(
            status_code=409, detail="A geração por IA não está disponível neste escritório."
        ) from exc
    except TimeoutError as exc:
        # Regra 11: geração longa demais vira erro claro, não requisição pendurada.
        raise HTTPException(
            status_code=504, detail="A geração passou do tempo limite. Tente instruções menores."
        ) from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"O modelo não respondeu: {exc}") from exc
    return _to_generation(result.generation, result.tool_labels)


@generations_router.get("/{generation_id}")
async def get_generation(
    generation_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> GenerationResponse:
    service = _service(session, current_user, provider)
    generation = await get_or_404(
        lambda: service.generations.get_by_id(generation_id), _GENERATION_NOT_FOUND
    )
    return _to_generation(generation)


@generations_router.post("/{generation_id}/to-template")
async def save_generation_as_template(
    generation_id: uuid.UUID,
    payload: SaveAsTemplateRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> SavedTemplateResponse:
    """Regra 12: é aqui — e só aqui — que a minuta vira documento do escritório."""
    service = _service(session, current_user, provider)
    generation = await get_or_404(
        lambda: service.generations.get_by_id(generation_id), _GENERATION_NOT_FOUND
    )
    template = await service.save_as_template(generation, user=current_user, name=payload.name)
    return SavedTemplateResponse(template_id=template.id, generation_id=generation.id)
