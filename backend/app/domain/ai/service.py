"""Camada de IA (spec 081): resolve a configuração da feature, chama o gateway com
fallback e registra o consumo.

Nenhum modelo é escolhido aqui (regra 2): vem de `ai_feature_config` ou do padrão do
ambiente. Nenhum provider concreto é importado (regra 1 + DIP): o service recebe um
`LLMProvider` — em teste, um fake que implementa o mesmo Protocol.
"""

import logging
import time
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.ai.exceptions import FeatureDisabledError, UnknownFeatureError
from app.domain.ai.features import FEATURE_KEYS
from app.domain.ai.models import AiFeatureConfig, AiUsage
from app.domain.ai.repository import AiFeatureConfigRepository, AiUsageRepository
from app.integrations.openrouter.types import (
    LLMChunk,
    LLMError,
    LLMProvider,
    LLMResponse,
    Message,
    ModelInfo,
    ToolSpec,
    Usage,
)

logger = logging.getLogger("rito.ai")

STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_FALLBACK = "fallback"

# Erro guardado em `ai_usage.error` — a coluna é para diagnóstico, não para log inteiro.
_MAX_ERROR_LENGTH = 500


@dataclass(frozen=True)
class ResolvedFeature:
    """A configuração efetiva de uma feature: o que a UI mostra e o que o runner usa."""

    feature_key: str
    model: str
    fallback_model: str | None
    temperature: float
    max_tokens: int | None
    is_enabled: bool
    store_prompts: bool
    # Regra 3: sem linha em `ai_feature_config`, roda com o padrão e AVISA — não falha.
    is_default: bool


class AiConfigService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.configs = AiFeatureConfigRepository(session)

    async def resolve(self, feature_key: str) -> ResolvedFeature:
        if feature_key not in FEATURE_KEYS:
            raise UnknownFeatureError(feature_key)
        settings = get_settings()
        config = await self.configs.get_by_feature(feature_key)
        if config is None:
            # Regra 3: aviso, nunca exceção — feature nova funciona antes de alguém
            # abrir a tela de configuração.
            logger.warning(
                "Feature de IA %s sem configuração — usando o modelo padrão do ambiente.",
                feature_key,
            )
            return ResolvedFeature(
                feature_key=feature_key,
                model=settings.openrouter_default_model,
                fallback_model=settings.openrouter_fallback_model,
                temperature=0.2,
                max_tokens=None,
                is_enabled=True,
                store_prompts=False,
                is_default=True,
            )
        return ResolvedFeature(
            feature_key=config.feature_key,
            model=config.model,
            fallback_model=config.fallback_model,
            temperature=float(config.temperature),
            max_tokens=config.max_tokens,
            is_enabled=config.is_enabled,
            store_prompts=config.store_prompts,
            is_default=False,
        )

    async def resolve_all(self) -> list[ResolvedFeature]:
        return [await self.resolve(key) for key in sorted(FEATURE_KEYS)]

    async def save(
        self,
        *,
        feature_key: str,
        model: str,
        fallback_model: str | None,
        temperature: float,
        max_tokens: int | None,
        is_enabled: bool,
        store_prompts: bool,
        actor_id: uuid.UUID,
    ) -> AiFeatureConfig:
        if feature_key not in FEATURE_KEYS:
            raise UnknownFeatureError(feature_key)
        config = await self.configs.get_by_feature(feature_key)
        if config is None:
            config = AiFeatureConfig(tenant_id=self.tenant_id, feature_key=feature_key, model=model)
        config.model = model
        config.fallback_model = fallback_model
        config.temperature = Decimal(str(temperature))
        config.max_tokens = max_tokens
        config.is_enabled = is_enabled
        config.store_prompts = store_prompts
        config.updated_by = actor_id
        return await self.configs.upsert(config)


class AiRunner:
    """Executa uma chamada de LLM de uma feature, com fallback e contabilidade.

    É a única porta por onde o resto do sistema fala com o modelo — as specs 082+
    consomem daqui, não do provider.
    """

    def __init__(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        provider: LLMProvider,
        *,
        catalog: Sequence[ModelInfo] | None = None,
        model_override: str | None = None,
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        # Spec 085, regra 9: o usuário escolheu o modelo para AQUELA conversa. Fica
        # acima da configuração da feature, e o uso é registrado com o modelo real.
        self.model_override = model_override
        self.provider = provider
        self.configs = AiConfigService(session, tenant_id)
        self.usage = AiUsageRepository(session)
        # Catálogo opcional: só serve para calcular custo quando a resposta não traz
        # (regra 7). Sem ele, `cost_usd` fica nulo em vez de virar zero mentiroso.
        self._catalog = {model.id: model for model in catalog or ()}

    async def run(
        self,
        *,
        feature_key: str,
        messages: Sequence[Message],
        user_id: uuid.UUID | None = None,
        tools: Sequence[ToolSpec] | None = None,
    ) -> LLMResponse:
        feature = await self.configs.resolve(feature_key)
        if not feature.is_enabled:
            raise FeatureDisabledError(feature_key)
        if self.model_override:
            feature = replace(feature, model=self.model_override)

        started = time.monotonic()
        try:
            response = await self._call(feature, messages, tools, feature.model)
        except LLMError as first_error:
            if feature.fallback_model is None:
                await self._record(
                    feature=feature,
                    model=feature.model,
                    status=STATUS_ERROR,
                    usage=Usage(),
                    latency_ms=_elapsed_ms(started),
                    user_id=user_id,
                    error=str(first_error),
                    messages=messages,
                    response=None,
                )
                await self._commit_usage()
                raise
            # Regra 5: UMA tentativa no fallback. Se ela também falhar, o erro que sobe
            # é o do fallback — é o último estado real da chamada.
            try:
                response = await self._call(feature, messages, tools, feature.fallback_model)
            except LLMError as fallback_error:
                await self._record(
                    feature=feature,
                    model=feature.fallback_model,
                    status=STATUS_ERROR,
                    usage=Usage(),
                    latency_ms=_elapsed_ms(started),
                    user_id=user_id,
                    error=f"{first_error} | fallback: {fallback_error}",
                    messages=messages,
                    response=None,
                )
                await self._commit_usage()
                raise
            await self._record(
                feature=feature,
                model=feature.fallback_model,
                status=STATUS_FALLBACK,
                usage=response.usage,
                latency_ms=_elapsed_ms(started),
                user_id=user_id,
                error=str(first_error),
                messages=messages,
                response=response,
            )
            return response

        await self._record(
            feature=feature,
            model=feature.model,
            status=STATUS_OK,
            usage=response.usage,
            latency_ms=_elapsed_ms(started),
            user_id=user_id,
            error=None,
            messages=messages,
            response=response,
        )
        return response

    async def _commit_usage(self) -> None:
        """Regra 6: o registro do uso precisa sobreviver à exceção que sobe.

        A sessão por request faz rollback em qualquer exceção (`get_session_for_
        current_user`) — sem este commit explícito, exatamente a chamada que falhou (a
        que mais interessa auditar) sumiria. Mesmo idioma da revogação de família em
        `AuthService.refresh()`, pelo mesmo motivo.
        """
        await self.session.commit()

    async def stream(
        self,
        *,
        feature_key: str,
        messages: Sequence[Message],
        user_id: uuid.UUID | None = None,
    ) -> AsyncIterator[LLMChunk]:
        """Streaming de token para as features que NÃO usam ferramenta (spec 088).

        Sem fallback de propósito (regra 5 da 081 vale para `complete`, não aqui): uma
        resposta já parcialmente entregue não pode ser refeita em outro modelo sem
        contradizer o que a pessoa já leu na tela. Falha no meio vira evento de erro, e
        o uso é registrado do mesmo jeito (regra 6 da 081).
        """
        feature = await self.configs.resolve(feature_key)
        if not feature.is_enabled:
            raise FeatureDisabledError(feature_key)
        started = time.monotonic()
        recebido = 0
        erro: str | None = None
        try:
            async for chunk in self.provider.stream(
                messages=messages,
                model=feature.model,
                temperature=feature.temperature,
                max_tokens=feature.max_tokens,
            ):
                if chunk.kind == "chunk" and chunk.content:
                    recebido += len(chunk.content)
                if chunk.kind == "error":
                    erro = chunk.error
                yield chunk
        finally:
            await self._record(
                feature=feature,
                model=feature.model,
                status=STATUS_ERROR if erro else STATUS_OK,
                # O protocolo só manda o uso no fim, e nem sempre manda: sem número
                # confiável, estimar por caractere é melhor que gravar zero.
                usage=Usage(completion_tokens=recebido // 4),
                latency_ms=_elapsed_ms(started),
                user_id=user_id,
                error=erro,
                messages=messages,
                response=None,
            )

    async def _call(
        self,
        feature: ResolvedFeature,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] | None,
        model: str,
    ) -> LLMResponse:
        return await self.provider.complete(
            messages=messages,
            model=model,
            tools=tools,
            temperature=feature.temperature,
            max_tokens=feature.max_tokens,
        )

    def _cost_for(self, model: str, usage: Usage) -> Decimal | None:
        """Regra 7: custo do próprio OpenRouter; ausente, calculado pelo catálogo."""
        if usage.cost_usd is not None:
            return Decimal(str(usage.cost_usd))
        info = self._catalog.get(model)
        if info is None:
            return None
        return Decimal(str(round(info.cost_for(usage), 6)))

    async def _record(
        self,
        *,
        feature: ResolvedFeature,
        model: str,
        status: str,
        usage: Usage,
        latency_ms: int,
        user_id: uuid.UUID | None,
        error: str | None,
        messages: Sequence[Message],
        response: LLMResponse | None,
    ) -> AiUsage:
        """Regra 6: todo uso é registrado, inclusive o que falhou.
        Regra 13: conteúdo só entra com opt-in explícito do tenant."""
        return await self.usage.record(
            AiUsage(
                tenant_id=self.tenant_id,
                user_id=user_id,
                feature_key=feature.feature_key,
                model=model,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                cost_usd=self._cost_for(model, usage),
                latency_ms=latency_ms,
                status=status,
                error=error[:_MAX_ERROR_LENGTH] if error else None,
                prompt=_render_prompt(messages) if feature.store_prompts else None,
                response_text=(
                    (response.content if response else None) if feature.store_prompts else None
                ),
            )
        )


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _render_prompt(messages: Sequence[Message]) -> str:
    return "\n\n".join(f"[{message.role}] {message.content}" for message in messages)
