from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.permissions import UserRole, require_role
from app.domain.ai.exceptions import UnknownFeatureError
from app.domain.ai.features import AI_FEATURES
from app.domain.ai.repository import AiUsageRepository
from app.domain.ai.schemas import (
    FeatureConfigListResponse,
    FeatureConfigRequest,
    FeatureConfigResponse,
    ModelCatalogResponse,
    ModelInfoResponse,
    UsageGroupResponse,
    UsageResponse,
    UsageTotalsResponse,
)
from app.domain.ai.service import AiConfigService, ResolvedFeature
from app.domain.auth.deps import get_session_for_current_user
from app.domain.users.models import User
from app.integrations.openrouter.types import LLMError, LLMNotConfiguredError, LLMProvider

router = APIRouter(prefix="/ai", tags=["ai"])

_LABELS = {feature.key: feature for feature in AI_FEATURES}


async def get_llm_provider(request: Request) -> LLMProvider:
    """O provider é montado uma vez no lifespan — nenhuma rota importa o client."""
    provider: LLMProvider = request.app.state.llm_provider
    return provider


def _to_config_response(resolved: ResolvedFeature) -> FeatureConfigResponse:
    feature = _LABELS[resolved.feature_key]
    return FeatureConfigResponse(
        feature_key=resolved.feature_key,
        label=feature.label,
        description=feature.description,
        model=resolved.model,
        fallback_model=resolved.fallback_model,
        temperature=resolved.temperature,
        max_tokens=resolved.max_tokens,
        is_enabled=resolved.is_enabled,
        store_prompts=resolved.store_prompts,
        is_default=resolved.is_default,
    )


@router.get("/models")
async def list_models(
    _current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    provider: LLMProvider = Depends(get_llm_provider),
) -> ModelCatalogResponse:
    """Catálogo do OpenRouter com preço (regra 7). Sem chave configurada, devolve vazio
    com `is_configured=false` — a UI explica; nada quebra (regra 11)."""
    try:
        models = await provider.models()
    except LLMNotConfiguredError:
        return ModelCatalogResponse(items=[], total=0, is_configured=False)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"Catálogo indisponível: {exc}") from exc
    return ModelCatalogResponse(
        items=[
            ModelInfoResponse(
                id=model.id,
                name=model.name,
                context_length=model.context_length,
                prompt_price_usd=model.prompt_price_usd,
                completion_price_usd=model.completion_price_usd,
            )
            for model in models
        ],
        total=len(models),
        is_configured=True,
    )


@router.get("/feature-config")
async def list_feature_config(
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
) -> FeatureConfigListResponse:
    service = AiConfigService(session=session, tenant_id=current_user.tenant_id)
    resolved = await service.resolve_all()
    return FeatureConfigListResponse(
        items=[_to_config_response(item) for item in resolved],
        is_configured=getattr(provider, "is_configured", False),
        default_model=get_settings().openrouter_default_model,
    )


@router.put("/feature-config")
async def put_feature_config(
    payload: FeatureConfigRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> FeatureConfigResponse:
    service = AiConfigService(session=session, tenant_id=current_user.tenant_id)
    try:
        await service.save(
            feature_key=payload.feature_key,
            model=payload.model,
            fallback_model=payload.fallback_model,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
            is_enabled=payload.is_enabled,
            store_prompts=payload.store_prompts,
            actor_id=current_user.id,
        )
    except UnknownFeatureError as exc:
        raise HTTPException(status_code=422, detail="Feature de IA desconhecida.") from exc
    return _to_config_response(await service.resolve(payload.feature_key))


@router.get("/usage")
async def get_usage(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    feature_key: str | None = Query(default=None),
    group_by: Literal["feature", "model", "status"] = Query(default="feature"),
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> UsageResponse:
    rows, totals = await AiUsageRepository(session).summary(
        from_=from_, to=to, feature_key=feature_key, group_by=group_by
    )
    return UsageResponse(
        group_by=group_by,
        **{"from": from_},
        to=to,
        items=[
            UsageGroupResponse(
                key=str(row.key),
                calls=int(row.calls),
                prompt_tokens=int(row.prompt_tokens),
                completion_tokens=int(row.completion_tokens),
                cost_usd=float(row.cost_usd or 0),
                errors=int(row.errors),
            )
            for row in rows
        ],
        totals=UsageTotalsResponse(
            calls=int(totals.calls),
            prompt_tokens=int(totals.prompt_tokens),
            completion_tokens=int(totals.completion_tokens),
            cost_usd=float(totals.cost_usd or 0),
            errors=int(totals.errors),
            avg_latency_ms=int(totals.avg_latency_ms) if totals.avg_latency_ms else None,
        ),
    )
