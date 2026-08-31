"""Camada LLM ponta a ponta (spec 081) — sem nenhuma chamada real (regra 12).

O provider dos testes é um fake que implementa `LLMProvider`: pelo LSP do CLAUDE.md
§5, ele é uma implementação de verdade da interface, não um mock de método. Assim o
que se exercita aqui é o `AiRunner` — resolução de modelo, fallback, contabilidade —
que é o que a spec 081 entrega.
"""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.ai.exceptions import FeatureDisabledError
from app.domain.ai.models import AiUsage
from app.domain.ai.service import AiConfigService, AiRunner
from app.domain.users.models import UserRole
from app.integrations.openrouter.types import (
    LLMChunk,
    LLMError,
    LLMResponse,
    Message,
    ModelInfo,
    ToolSpec,
    Usage,
)
from tests.integration.conftest import SeededUser, auth_header

FEATURE = "publication_summary"
CONFIGURED_MODEL = "fabricante-x/modelo-configurado"
FALLBACK_MODEL = "fabricante-x/modelo-reserva"

CATALOG = [
    ModelInfo(
        id=CONFIGURED_MODEL,
        name="Modelo configurado",
        context_length=128000,
        prompt_price_usd=0.000002,
        completion_price_usd=0.000008,
    )
]


class FakeProvider:
    """Implementação de `LLMProvider` para teste (LSP) — registra o que foi chamado."""

    def __init__(
        self,
        *,
        fail_models: Sequence[str] = (),
        cost_usd: float | None = None,
        is_configured: bool = True,
    ) -> None:
        self.calls: list[str] = []
        self._fail_models = set(fail_models)
        self._cost_usd = cost_usd
        self.is_configured = is_configured

    async def complete(
        self,
        *,
        messages: Sequence[Message],
        model: str,
        tools: Sequence[ToolSpec] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.calls.append(model)
        if model in self._fail_models:
            raise LLMError(f"modelo {model} indisponível")
        return LLMResponse(
            content="Resumo gerado.",
            usage=Usage(prompt_tokens=1000, completion_tokens=500, cost_usd=self._cost_usd),
            model=model,
            finish_reason="stop",
        )

    async def stream(self, **kwargs: object) -> AsyncIterator[LLMChunk]:  # pragma: no cover
        yield LLMChunk(kind="done")

    async def models(self) -> list[ModelInfo]:
        return list(CATALOG)


async def _configure(
    session_factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    **overrides: object,
) -> None:
    async with session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        service = AiConfigService(session=session, tenant_id=tenant_id)
        await service.save(
            feature_key=FEATURE,
            model=str(overrides.get("model", CONFIGURED_MODEL)),
            fallback_model=overrides.get("fallback_model"),  # type: ignore[arg-type]
            temperature=float(overrides.get("temperature", 0.2)),  # type: ignore[arg-type]
            max_tokens=None,
            is_enabled=bool(overrides.get("is_enabled", True)),
            store_prompts=bool(overrides.get("store_prompts", False)),
            actor_id=actor_id,
        )


async def _run(
    session_factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    provider: FakeProvider,
    *,
    user_id: uuid.UUID | None = None,
    catalog: Sequence[ModelInfo] | None = None,
) -> LLMResponse:
    async with session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        runner = AiRunner(session, tenant_id, provider, catalog=catalog)
        return await runner.run(
            feature_key=FEATURE,
            messages=[Message(role="user", content="Resuma esta intimação.")],
            user_id=user_id,
        )


async def _usages(
    session_factory: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID
) -> list[AiUsage]:
    async with session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        return list((await session.scalars(select(AiUsage).order_by(AiUsage.created_at))).all())


async def test_modelo_vem_da_configuracao_da_feature(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 2: trocar o modelo pela configuração muda a chamada, sem deploy."""
    gestor = await make_user(role=UserRole.GESTOR)
    await _configure(app_session_factory, gestor.tenant_id, gestor.user_id)
    provider = FakeProvider()

    await _run(app_session_factory, gestor.tenant_id, provider)

    assert provider.calls == [CONFIGURED_MODEL]
    usage = (await _usages(app_session_factory, gestor.tenant_id))[0]
    assert usage.model == CONFIGURED_MODEL
    assert usage.status == "ok"


async def test_sem_configuracao_usa_o_padrao_do_ambiente_e_avisa(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regra 3: feature sem linha de configuração roda com o padrão — nunca falha."""
    from app.core.config import get_settings

    gestor = await make_user(role=UserRole.GESTOR)
    provider = FakeProvider()

    with caplog.at_level("WARNING", logger="rito.ai"):
        await _run(app_session_factory, gestor.tenant_id, provider)

    assert provider.calls == [get_settings().openrouter_default_model]
    assert any("sem configuração" in record.getMessage() for record in caplog.records)


async def test_feature_desligada_recusa_a_chamada(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 4: `is_enabled = false` desliga de verdade — não é só a UI escondendo."""
    gestor = await make_user(role=UserRole.GESTOR)
    await _configure(app_session_factory, gestor.tenant_id, gestor.user_id, is_enabled=False)
    provider = FakeProvider()

    with pytest.raises(FeatureDisabledError):
        await _run(app_session_factory, gestor.tenant_id, provider)

    assert provider.calls == []


async def test_falha_aciona_o_fallback_uma_vez(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 5: uma tentativa no reserva, registrada como `fallback`."""
    gestor = await make_user(role=UserRole.GESTOR)
    await _configure(
        app_session_factory, gestor.tenant_id, gestor.user_id, fallback_model=FALLBACK_MODEL
    )
    provider = FakeProvider(fail_models=[CONFIGURED_MODEL])

    response = await _run(app_session_factory, gestor.tenant_id, provider)

    assert response.model == FALLBACK_MODEL
    assert provider.calls == [CONFIGURED_MODEL, FALLBACK_MODEL]
    usages = await _usages(app_session_factory, gestor.tenant_id)
    assert len(usages) == 1, "o fallback é UMA chamada do ponto de vista da feature"
    assert usages[0].status == "fallback"
    assert usages[0].model == FALLBACK_MODEL
    assert usages[0].error is not None


async def test_uso_e_registrado_mesmo_quando_a_chamada_falha(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 6: erro sem registro é custo invisível."""
    gestor = await make_user(role=UserRole.GESTOR)
    await _configure(app_session_factory, gestor.tenant_id, gestor.user_id)
    provider = FakeProvider(fail_models=[CONFIGURED_MODEL])

    with pytest.raises(LLMError):
        await _run(app_session_factory, gestor.tenant_id, provider)

    usage = (await _usages(app_session_factory, gestor.tenant_id))[0]
    assert usage.status == "error"
    assert usage.error is not None
    assert usage.latency_ms is not None


async def test_custo_calculado_pelo_catalogo_quando_o_gateway_nao_manda(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 7: sem custo na resposta, vale o preço do catálogo; sem catálogo, nulo —
    nunca zero, que leria como "de graça"."""
    gestor = await make_user(role=UserRole.GESTOR)
    await _configure(app_session_factory, gestor.tenant_id, gestor.user_id)

    await _run(app_session_factory, gestor.tenant_id, FakeProvider(), catalog=CATALOG)
    esperado = Decimal(str(round(1000 * 0.000002 + 500 * 0.000008, 6)))
    assert (await _usages(app_session_factory, gestor.tenant_id))[0].cost_usd == esperado

    outro = await make_user(role=UserRole.GESTOR)
    await _configure(app_session_factory, outro.tenant_id, outro.user_id)
    await _run(app_session_factory, outro.tenant_id, FakeProvider())
    assert (await _usages(app_session_factory, outro.tenant_id))[0].cost_usd is None


@pytest.mark.commits
async def test_prompt_nao_e_persistido_sem_opt_in(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 13 (LGPD): por padrão só metadados; conteúdo exige opt-in do tenant."""
    gestor = await make_user(role=UserRole.GESTOR)
    await _configure(app_session_factory, gestor.tenant_id, gestor.user_id)
    await _run(app_session_factory, gestor.tenant_id, FakeProvider())

    padrao = (await _usages(app_session_factory, gestor.tenant_id))[0]
    assert padrao.prompt is None
    assert padrao.response_text is None

    await _configure(app_session_factory, gestor.tenant_id, gestor.user_id, store_prompts=True)
    await _run(app_session_factory, gestor.tenant_id, FakeProvider())

    com_opt_in = (await _usages(app_session_factory, gestor.tenant_id))[1]
    assert com_opt_in.prompt is not None and "Resuma esta intimação." in com_opt_in.prompt
    assert com_opt_in.response_text == "Resumo gerado."


async def test_sem_chave_o_catalogo_vem_vazio_e_a_ui_avisa(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 11: sem `OPENROUTER_API_KEY` as features aparecem desabilitadas e o
    sistema continua de pé — nenhuma rota devolve 500."""
    from app.domain.ai.router import get_llm_provider
    from app.integrations.openrouter.types import LLMNotConfiguredError
    from app.main import app

    class UnconfiguredProvider(FakeProvider):
        async def models(self) -> list[ModelInfo]:
            raise LLMNotConfiguredError("sem chave")

    gestor = await make_user(role=UserRole.GESTOR)
    app.dependency_overrides[get_llm_provider] = lambda: UnconfiguredProvider(is_configured=False)
    try:
        catalogo = await client.get("/api/v1/ai/models", headers=auth_header(gestor))
        config = await client.get("/api/v1/ai/feature-config", headers=auth_header(gestor))
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)

    assert catalogo.status_code == 200
    assert catalogo.json() == {"items": [], "total": 0, "is_configured": False}
    assert config.status_code == 200
    assert config.json()["is_configured"] is False
    # A lista de features continua vindo: o usuário configura antes de ter chave.
    assert len(config.json()["items"]) >= 5


async def test_painel_de_consumo_agrupa_e_totaliza(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    await _configure(
        app_session_factory, gestor.tenant_id, gestor.user_id, fallback_model=FALLBACK_MODEL
    )
    await _run(app_session_factory, gestor.tenant_id, FakeProvider(cost_usd=0.01))
    await _run(
        app_session_factory,
        gestor.tenant_id,
        FakeProvider(fail_models=[CONFIGURED_MODEL], cost_usd=0.02),
    )

    response = await client.get(
        "/api/v1/ai/usage", params={"group_by": "status"}, headers=auth_header(gestor)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["totals"]["calls"] == 2
    assert round(body["totals"]["cost_usd"], 4) == 0.03
    assert {item["key"] for item in body["items"]} == {"ok", "fallback"}
