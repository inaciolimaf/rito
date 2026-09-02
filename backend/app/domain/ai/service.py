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
from datetime import date
from decimal import Decimal
from typing import Any

from opentelemetry.trace import SpanKind
from sqlalchemy import Row
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.observability.metrics import record_llm_usage
from app.core.observability.tracing import get_tracer
from app.domain.ai.budget import AiBudgetService
from app.domain.ai.exceptions import FeatureDisabledError, UnknownFeatureError
from app.domain.ai.features import FEATURE_KEYS, FEATURES_BY_KEY
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


def _feature_from_env(feature_key: str, settings: Settings) -> ResolvedFeature:
    """A feature que ninguém configurou ainda, resolvida pelo ambiente (regra 3).

    Aviso, nunca exceção: feature de IA nova precisa funcionar antes de alguém abrir a tela
    de configuração, senão o deploy que a introduz derruba a tela que a usa. `is_default`
    marca a linha como não-configurada para a UI poder dizer isso ao usuário.

    O tier escolhe entre o modelo econômico e o padrão — é a única decisão de custo que o
    código toma sozinho, e ela existe porque feature econômica sem configuração cair no
    modelo caro seria a forma silenciosa de estourar o teto da spec 090.
    """
    logger.warning(
        "Feature de IA %s sem configuração — usando o modelo padrão do ambiente.",
        feature_key,
    )
    return ResolvedFeature(
        feature_key=feature_key,
        model=(
            settings.openrouter_economy_model
            if FEATURES_BY_KEY[feature_key].tier == "economico"
            else settings.openrouter_default_model
        ),
        fallback_model=settings.openrouter_fallback_model,
        temperature=0.2,
        max_tokens=None,
        is_enabled=True,
        store_prompts=False,
        is_default=True,
    )


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
            return _feature_from_env(feature_key, settings)
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


class AiUsageService:
    """Leitura do consumo de IA (spec 080). Existe para o router não falar com o
    repositório (spec 118, checagem 2): a rota `/ai/usage` monta a resposta HTTP, quem
    sabe agrupar e somar é esta camada."""

    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.usage = AiUsageRepository(session)

    async def summary(
        self,
        *,
        from_: date | None,
        to: date | None,
        feature_key: str | None,
        group_by: str,
    ) -> tuple[Sequence[Row[Any]], Row[Any]]:
        return await self.usage.summary(
            from_=from_, to=to, feature_key=feature_key, group_by=group_by
        )


@dataclass(frozen=True, slots=True)
class CallOutcome:
    """O que aconteceu numa chamada ao provedor — o que `ai_usage` registra (regra 6).

    Spec 116: `_record` recebia nove parâmetros, e seis deles descreviam o MESMO evento.
    A separação que o objeto torna visível é entre o que a chamada PEDIU (feature, usuário,
    mensagens) e o que ela DEU (modelo efetivo, status, consumo, latência, erro, resposta) —
    e ela importa porque o modelo efetivo pode não ser o pedido: no fallback da regra 5 o
    `model` aqui é o de reserva, enquanto a `feature` continua sendo a mesma.
    """

    model: str
    status: str
    usage: Usage
    latency_ms: int
    error: str | None = None
    response: LLMResponse | None = None


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
        commit_usage: bool = True,
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        # Spec 085, regra 9: o usuário escolheu o modelo para AQUELA conversa. Fica
        # acima da configuração da feature, e o uso é registrado com o modelo real.
        self.model_override = model_override
        self.provider = provider
        self.configs = AiConfigService(session, tenant_id)
        self.usage = AiUsageRepository(session)
        self.budget = AiBudgetService(session, tenant_id)
        # Spec 094: quem é DONO da transação desliga isto. O commit de emergência da
        # regra 6 existe para a sessão-por-request, que faz rollback ao subir a exceção;
        # dentro de um `session.begin()` de quem chama, ele encerraria o bloco no meio e
        # levaria junto a operação que estava em curso.
        self.commit_usage = commit_usage
        # Catálogo opcional: só serve para calcular custo quando a resposta não traz
        # (regra 7). Sem ele, `cost_usd` fica nulo em vez de virar zero mentiroso.
        self._catalog = {model.id: model for model in catalog or ()}

    async def _enabled_feature(self, feature_key: str) -> ResolvedFeature:
        """A configuração da feature, já com o override de modelo aplicado.

        Feature desligada levanta antes de qualquer gasto. O override existe para o
        usuário trocar o modelo na UI (CLAUDE.md §7, regra 2) — modelo é configuração,
        nunca código.
        """
        feature = await self.configs.resolve(feature_key)
        if not feature.is_enabled:
            raise FeatureDisabledError(feature_key)
        if self.model_override:
            feature = replace(feature, model=self.model_override)
        return feature

    async def _record_error(
        self,
        feature: ResolvedFeature,
        model: str,
        motivo: str,
        *,
        started: float,
        user_id: uuid.UUID | None,
        messages: Sequence[Message],
    ) -> None:
        """Registra a chamada que falhou E COMITA, antes de a exceção subir (regra 6).

        O commit explícito é o ponto: a sessão por request faz rollback em qualquer
        exceção, e sem ele exatamente a chamada que falhou — a que mais interessa auditar —
        sumiria junto. Vale para os dois caminhos de falha, e é por isso que eles são o
        mesmo método.
        """
        await self._record(
            CallOutcome(
                model=model,
                status=STATUS_ERROR,
                usage=Usage(),
                latency_ms=_elapsed_ms(started),
                error=motivo,
            ),
            feature=feature,
            user_id=user_id,
            messages=messages,
        )
        await self._commit_usage()

    async def _record_fallback(
        self,
        response: LLMResponse,
        feature: ResolvedFeature,
        model: str,
        first_error: LLMError,
        started: float,
        user_id: uuid.UUID | None,
        messages: Sequence[Message],
    ) -> None:
        """Registra a chamada que só deu certo na reserva.

        O status é `STATUS_FALLBACK` e não `STATUS_OK` de propósito: para o usuário a
        resposta chegou, mas para quem opera é um modelo principal falhando — e uma
        sequência disso é o sinal de que a configuração da feature precisa mudar. O erro
        original viaja junto pelo mesmo motivo.

        `model` vem por parâmetro e não de `feature.fallback_model` porque quem chama já
        provou que ele não é nulo, e repetir a checagem aqui seria um ramo morto.
        """
        await self._record(
            CallOutcome(
                model=model,
                status=STATUS_FALLBACK,
                usage=response.usage,
                latency_ms=_elapsed_ms(started),
                error=str(first_error),
                response=response,
            ),
            feature=feature,
            user_id=user_id,
            messages=messages,
        )

    async def _try_fallback(
        self,
        *,
        feature: ResolvedFeature,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] | None,
        first_error: LLMError,
        started: float,
        user_id: uuid.UUID | None,
    ) -> LLMResponse:
        """O que acontece depois que o modelo principal falhou (regra 5).

        Sem modelo de reserva configurado, o erro original sobe — mas só depois de
        registrado: é justamente a chamada que falhou que mais interessa auditar, e é por
        isso que `_commit_usage` vem antes do `raise` nos dois caminhos.

        Com reserva, é UMA tentativa. Falhando ela também, o erro que sobe é o DELA, com
        o primeiro no texto: o último estado real da chamada é o que o operador precisa
        ler primeiro, e o anterior é contexto.
        """
        if feature.fallback_model is None:
            await self._record_error(
                feature,
                feature.model,
                str(first_error),
                started=started,
                user_id=user_id,
                messages=messages,
            )
            raise first_error

        try:
            response = await self._call(feature, messages, tools, feature.fallback_model)
        except LLMError as fallback_error:
            await self._record_error(
                feature,
                feature.fallback_model,
                f"{first_error} | fallback: {fallback_error}",
                started=started,
                user_id=user_id,
                messages=messages,
            )
            raise
        await self._record_fallback(
            response, feature, feature.fallback_model, first_error, started, user_id, messages
        )
        return response

    async def _record_success(
        self,
        response: LLMResponse,
        feature: ResolvedFeature,
        started: float,
        user_id: uuid.UUID | None,
        messages: Sequence[Message],
    ) -> None:
        """O registro em `ai_usage` da chamada que deu certo (regra 7 do CLAUDE.md).

        A latência é medida a partir de `started`, que é anterior ao `_call` — inclui de
        propósito o tempo do fallback quando houve um, porque é esse o tempo que o usuário
        esperou.
        """
        await self._record(
            CallOutcome(
                model=feature.model,
                status=STATUS_OK,
                usage=response.usage,
                latency_ms=_elapsed_ms(started),
                response=response,
            ),
            feature=feature,
            user_id=user_id,
            messages=messages,
        )

    async def _cached(
        self, feature_key: str, feature: ResolvedFeature, messages: Sequence[Message]
    ) -> LLMResponse | None:
        """A resposta já paga para esta mesma pergunta, se existir.

        A chave inclui o modelo: trocar o modelo da feature invalida o cache inteiro dela,
        e tem que invalidar mesmo — a resposta de um modelo não vale pela do outro.
        """
        return await self.budget.cached(
            feature_key=feature_key, model=feature.model, messages=messages
        )

    async def run(
        self,
        *,
        feature_key: str,
        messages: Sequence[Message],
        user_id: uuid.UUID | None = None,
        tools: Sequence[ToolSpec] | None = None,
        use_cache: bool = False,
    ) -> LLMResponse:
        """Uma chamada ao modelo da feature, com teto de custo, cache e reserva.

        A ORDEM aqui é a regra, não conveniência:

        1. **Teto antes de gastar** (spec 090, alvo 2). Checar depois seria cobrar a chamada
           e negar o resultado ao usuário.
        2. **Cache antes de chamar.** O `and` curto-circuita: sem `use_cache` a consulta ao
           cache nem acontece, e o caminho sem cache custa o mesmo de antes da 090. O
           `is not None` é explícito porque a pergunta é «tem resposta guardada?», não «a
           resposta guardada é verdadeira?» — hoje coincidem, e podem divergir.
        3. **Reserva só depois do erro** (regra 5). O tempo é contado desde antes da
           primeira tentativa, então a latência registrada é a que o usuário esperou.
        """
        feature = await self._enabled_feature(feature_key)
        await self.budget.ensure_within_budget()
        if (
            use_cache
            and (em_cache := await self._cached(feature_key, feature, messages)) is not None
        ):
            return em_cache
        started = time.monotonic()
        try:
            response = await self._call(feature, messages, tools, feature.model)
        except LLMError as first_error:
            return await self._try_fallback(
                feature=feature,
                messages=messages,
                tools=tools,
                first_error=first_error,
                started=started,
                user_id=user_id,
            )

        await self._record_success(response, feature, started, user_id, messages)
        if use_cache:
            await self.budget.store(
                feature_key=feature_key,
                model=feature.model,
                messages=messages,
                response=response,
            )
        return response

    async def _commit_usage(self) -> None:
        if not self.commit_usage:
            # O registro do uso viaja na transação de quem chama — que ou termina (e
            # grava) ou volta atrás inteira (e aí a chamada também não aconteceu).
            return
        """Regra 6: o registro do uso precisa sobreviver à exceção que sobe.

        A sessão por request faz rollback em qualquer exceção (`get_session_for_
        current_user`) — sem este commit explícito, exatamente a chamada que falhou (a
        que mais interessa auditar) sumiria. Mesmo idioma da revogação de família em
        `AuthService.refresh()`, pelo mesmo motivo.
        """
        await self.session.commit()

    async def _record_stream(
        self,
        feature: ResolvedFeature,
        erro: str | None,
        recebido: int,
        *,
        started: float,
        user_id: uuid.UUID | None,
        messages: Sequence[Message],
    ) -> None:
        """O uso de uma resposta em streaming, registrado no `finally` (regra 6 da 081).

        O protocolo só manda o consumo de tokens no fim, e nem sempre manda. Sem número
        confiável, estimar por caractere (≈4 por token) é melhor que gravar zero: zero
        entraria na soma do teto de custo da spec 090 como se a chamada fosse grátis.
        """
        await self._record(
            CallOutcome(
                model=feature.model,
                status=STATUS_ERROR if erro else STATUS_OK,
                usage=Usage(completion_tokens=recebido // 4),
                latency_ms=_elapsed_ms(started),
                error=erro,
            ),
            feature=feature,
            user_id=user_id,
            messages=messages,
        )

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
        await self.budget.ensure_within_budget()
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
            await self._record_stream(
                feature, erro, recebido, started=started, user_id=user_id, messages=messages
            )

    async def _call(
        self,
        feature: ResolvedFeature,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] | None,
        model: str,
    ) -> LLMResponse:
        # Spec 097, regra 4: span de LLM. O nome carrega a feature, não o modelo —
        # trocar de modelo é configuração (CLAUDE.md §7, regra 2) e não deveria
        # renomear a operação no trace; o modelo vai como atributo.
        with get_tracer().start_as_current_span(
            f"llm {feature.feature_key}",
            kind=SpanKind.CLIENT,
            attributes={"gen_ai.system": "openrouter", "gen_ai.request.model": model},
        ):
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

    def _usage_row(
        self,
        outcome: CallOutcome,
        custo: Decimal | None,
        *,
        feature: ResolvedFeature,
        user_id: uuid.UUID | None,
        messages: Sequence[Message],
    ) -> AiUsage:
        """A linha de `ai_usage`. Regra 13: conteúdo só entra com opt-in do tenant.

        `store_prompts` decide prompt e resposta JUNTOS — guardar um sem o outro daria um
        registro que não serve para depurar (pergunta sem resposta) nem para auditar
        (resposta sem pergunta), e ainda assim guardaria conteúdo do cliente.
        """
        return AiUsage(
            tenant_id=self.tenant_id,
            user_id=user_id,
            feature_key=feature.feature_key,
            model=outcome.model,
            prompt_tokens=outcome.usage.prompt_tokens,
            completion_tokens=outcome.usage.completion_tokens,
            cost_usd=custo,
            latency_ms=outcome.latency_ms,
            status=outcome.status,
            error=outcome.error[:_MAX_ERROR_LENGTH] if outcome.error else None,
            prompt=_render_prompt(messages) if feature.store_prompts else None,
            response_text=(
                (outcome.response.content if outcome.response else None)
                if feature.store_prompts
                else None
            ),
        )

    async def _record(
        self,
        outcome: CallOutcome,
        *,
        feature: ResolvedFeature,
        user_id: uuid.UUID | None,
        messages: Sequence[Message],
    ) -> AiUsage:
        """Regra 6: todo uso é registrado, inclusive o que falhou.
        Regra 13: conteúdo só entra com opt-in explícito do tenant."""
        model, usage = outcome.model, outcome.usage
        custo = self._cost_for(model, usage)
        # Spec 097, regra 6: tokens e custo de LLM também viram métrica. Aqui, e não no
        # provider, porque este é o único ponto por onde TODA chamada passa — inclusive
        # a que falhou e a que caiu no fallback.
        record_llm_usage(
            feature=feature.feature_key,
            model=model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            cost_usd=float(custo) if custo is not None else 0.0,
        )
        return await self.usage.record(
            self._usage_row(outcome, custo, feature=feature, user_id=user_id, messages=messages)
        )


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _render_prompt(messages: Sequence[Message]) -> str:
    return "\n\n".join(f"[{message.role}] {message.content}" for message in messages)
