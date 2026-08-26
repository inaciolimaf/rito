"""Teto de gasto, cache e alerta de anomalia (spec 090, alvo 2).

IA sem teto é conta surpresa no fim do mês. O que se exercita aqui é a política: o
bloqueio acontece ANTES de gastar, o alerta de 80% não bloqueia nada, e o escritório que
prefere estourar a parar no meio de um prazo pode desligar só o bloqueio.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.ai.budget import AiBudgetService, BudgetExceededError
from app.domain.ai.models import AiUsage
from app.domain.ai.service import AiRunner
from app.domain.users.models import UserRole
from app.integrations.openrouter.types import Message
from tests.integration.conftest import SeededUser, auth_header
from tests.integration.test_ai_analytics import _reset_overrides, _sql  # noqa: F401
from tests.integration.test_ai_copilot import ScriptedProvider, _use
from tests.integration.test_ai_layer import FEATURE, FakeProvider

pytestmark = pytest.mark.asyncio


async def _gastar(
    session_factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    *,
    valor: str,
    feature_key: str = FEATURE,
    quando: datetime | None = None,
) -> None:
    """Gasto histórico direto em `ai_usage` — é de lá que o teto lê (nenhum segundo
    contador para divergir do primeiro)."""
    async with session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        uso = AiUsage(
            tenant_id=tenant_id,
            feature_key=feature_key,
            model="fabricante-x/modelo-configurado",
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=Decimal(valor),
            latency_ms=10,
            status="ok",
        )
        session.add(uso)
        await session.flush()
        if quando is not None:
            uso.created_at = quando


async def _definir_teto(
    session_factory: async_sessionmaker[AsyncSession],
    user: SeededUser,
    *,
    limite: str | None,
    alerta: int = 80,
    bloqueia: bool = True,
) -> None:
    async with session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        await AiBudgetService(session, user.tenant_id).save(
            limit_usd=Decimal(limite) if limite is not None else None,
            alert_pct=alerta,
            is_blocking=bloqueia,
            actor_id=user.user_id,
        )


async def _rodar(
    session_factory: async_sessionmaker[AsyncSession],
    tenant_id: uuid.UUID,
    provider: FakeProvider,
    *,
    pergunta: str = "Resuma esta intimação.",
    use_cache: bool = False,
) -> str | None:
    async with session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        runner = AiRunner(session, tenant_id, provider)
        resposta = await runner.run(
            feature_key=FEATURE,
            messages=[Message(role="user", content=pergunta)],
            use_cache=use_cache,
        )
        return resposta.content


async def test_sem_teto_configurado_nada_bloqueia(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Estado de quem nunca abriu a tela: o painel mostra o gasto e a IA funciona."""
    user = await make_user(role=UserRole.ADMINISTRADOR)
    await _gastar(app_session_factory, user.tenant_id, valor="12.34")

    provider = FakeProvider()
    assert await _rodar(app_session_factory, user.tenant_id, provider) == "Resumo gerado."
    assert provider.calls, "sem teto, a chamada tem de acontecer"


async def test_bloqueia_em_100_por_cento_antes_de_chamar_o_modelo(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """O bloqueio é ANTES da chamada: bloquear depois seria pagar e negar o resultado."""
    user = await make_user(role=UserRole.ADMINISTRADOR)
    await _definir_teto(app_session_factory, user, limite="10.00")
    await _gastar(app_session_factory, user.tenant_id, valor="10.00")

    provider = FakeProvider()
    with pytest.raises(BudgetExceededError):
        await _rodar(app_session_factory, user.tenant_id, provider)

    assert provider.calls == [], "o modelo não pode ter sido chamado"


async def test_alerta_em_80_por_cento_nao_bloqueia(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await make_user(role=UserRole.ADMINISTRADOR)
    await _definir_teto(app_session_factory, user, limite="10.00")
    await _gastar(app_session_factory, user.tenant_id, valor="8.50")

    provider = FakeProvider()
    assert await _rodar(app_session_factory, user.tenant_id, provider) == "Resumo gerado."

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        situacao = await AiBudgetService(session, user.tenant_id).status()
    assert situacao.should_alert is True
    assert situacao.exceeded is False


async def test_bloqueio_desligado_mantem_o_alerta_e_deixa_passar(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Há escritório que prefere estourar o teto a parar no meio de um prazo."""
    user = await make_user(role=UserRole.ADMINISTRADOR)
    await _definir_teto(app_session_factory, user, limite="10.00", bloqueia=False)
    await _gastar(app_session_factory, user.tenant_id, valor="15.00")

    provider = FakeProvider()
    assert await _rodar(app_session_factory, user.tenant_id, provider) == "Resumo gerado."

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        situacao = await AiBudgetService(session, user.tenant_id).status()
    assert situacao.exceeded is True


async def test_gasto_do_mes_anterior_nao_conta_no_teto(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """O teto é MENSAL: virar o mês zera o contador, senão o escritório ficaria travado
    para sempre depois do primeiro estouro."""
    user = await make_user(role=UserRole.ADMINISTRADOR)
    await _definir_teto(app_session_factory, user, limite="10.00")
    inicio_do_mes = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    await _gastar(
        app_session_factory,
        user.tenant_id,
        valor="99.00",
        quando=inicio_do_mes - timedelta(days=1),
    )

    provider = FakeProvider()
    assert await _rodar(app_session_factory, user.tenant_id, provider) == "Resumo gerado."


async def test_o_teto_de_um_escritorio_nao_afeta_o_outro(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    a = await make_user(role=UserRole.ADMINISTRADOR)
    b = await make_user(role=UserRole.ADMINISTRADOR)
    await _definir_teto(app_session_factory, a, limite="1.00")
    await _gastar(app_session_factory, a.tenant_id, valor="5.00")

    provider = FakeProvider()
    with pytest.raises(BudgetExceededError):
        await _rodar(app_session_factory, a.tenant_id, provider)
    assert await _rodar(app_session_factory, b.tenant_id, provider) == "Resumo gerado."


async def test_cache_evita_pagar_duas_vezes_pela_mesma_entrada(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Entrada idêntica em janela curta (clique duplo, nova tentativa depois de erro)."""
    user = await make_user(role=UserRole.ADMINISTRADOR)
    provider = FakeProvider()

    await _rodar(app_session_factory, user.tenant_id, provider, use_cache=True)
    await _rodar(app_session_factory, user.tenant_id, provider, use_cache=True)

    assert len(provider.calls) == 1, "a segunda vez tem de vir do cache"


async def test_cache_e_por_escritorio(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Resposta cacheada de um tenant nunca é servida a outro — o RLS vale aqui também."""
    a = await make_user(role=UserRole.ADMINISTRADOR)
    b = await make_user(role=UserRole.ADMINISTRADOR)
    provider = FakeProvider()

    await _rodar(app_session_factory, a.tenant_id, provider, use_cache=True)
    await _rodar(app_session_factory, b.tenant_id, provider, use_cache=True)

    assert len(provider.calls) == 2


async def test_entrada_diferente_nao_reaproveita_resposta(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await make_user(role=UserRole.ADMINISTRADOR)
    provider = FakeProvider()

    await _rodar(app_session_factory, user.tenant_id, provider, use_cache=True)
    await _rodar(
        app_session_factory, user.tenant_id, provider, pergunta="Outra coisa.", use_cache=True
    )

    assert len(provider.calls) == 2


async def test_alerta_quando_a_feature_gasta_3x_a_media_historica(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Média DELA, não das outras: o copiloto custa naturalmente mais que uma
    classificação, e comparar features entre si só produziria ruído."""
    user = await make_user(role=UserRole.ADMINISTRADOR)
    ontem = datetime.now(UTC).replace(hour=12) - timedelta(days=1)
    # 30 dias de histórico somando US$ 3,00 → média diária de US$ 0,10.
    await _gastar(app_session_factory, user.tenant_id, valor="3.00", quando=ontem)
    await _gastar(app_session_factory, user.tenant_id, valor="1.00")

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        anomalias = await AiBudgetService(session, user.tenant_id).anomalies()

    assert [item.feature_key for item in anomalias] == [FEATURE]
    assert anomalias[0].factor == 10.0


async def test_feature_estreando_hoje_nao_vira_anomalia(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Sem histórico não há do que se desviar — o primeiro dia de uso é estreia."""
    user = await make_user(role=UserRole.ADMINISTRADOR)
    await _gastar(app_session_factory, user.tenant_id, valor="50.00")

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        anomalias = await AiBudgetService(session, user.tenant_id).anomalies()

    assert anomalias == []


async def test_rotas_de_orcamento_leem_e_gravam(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = await make_user(role=UserRole.ADMINISTRADOR)
    await _gastar(app_session_factory, user.tenant_id, valor="4.00")

    salvo = await client.put(
        "/api/v1/ai/budget",
        json={"monthly_limit_usd": "5.00", "alert_pct": 80, "is_blocking": True},
        headers=auth_header(user),
    )
    assert salvo.status_code == 200
    assert salvo.json()["used_pct"] == 80.0
    assert salvo.json()["is_alerting"] is True
    assert salvo.json()["is_exceeded"] is False

    lido = await client.get("/api/v1/ai/budget", headers=auth_header(user))
    assert lido.status_code == 200
    assert lido.json()["monthly_limit_usd"] == 5.0
    assert lido.json()["spent_usd"] == 4.0


async def test_orcamento_e_de_administrador(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador = await make_user(role=UserRole.COLABORADOR)
    resposta = await client.get("/api/v1/ai/budget", headers=auth_header(colaborador))
    assert resposta.status_code == 403


async def test_teto_estourado_vira_409_com_os_numeros(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A UI precisa poder dizer quanto falta, não só 'não deu'."""
    user = await make_user(role=UserRole.ADMINISTRADOR)
    await _definir_teto(app_session_factory, user, limite="1.00")
    await _gastar(app_session_factory, user.tenant_id, valor="2.00")

    _use(ScriptedProvider(script=[_sql("SELECT 1")]))
    resposta = await client.post(
        "/api/v1/ai/analytics/ask",
        json={"question": "Quantos processos entraram este mês?", "confirm_sql": None},
        headers=auth_header(user),
    )

    assert resposta.status_code == 409
    corpo = resposta.json()
    assert corpo["spent_usd"] == 2.0
    assert corpo["limit_usd"] == 1.0


def test_feature_economica_cai_no_modelo_barato_por_padrao() -> None:
    """Alvo 2: classificar um ato e resumir três parágrafos não precisam do modelo mais
    caro. O escritório continua podendo trocar na UI — isto é o padrão de quem nunca
    trocou, e é onde está a maior parte do consumo."""
    from app.domain.ai.features import FEATURES_BY_KEY

    assert FEATURES_BY_KEY["publication_summary"].tier == "economico"
    assert FEATURES_BY_KEY["copilot"].tier == "padrao"


async def test_configuracao_do_escritorio_vence_o_tier(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 2 da 081 continua valendo: o tier decide o PADRÃO, nunca sobrepõe escolha."""
    from app.domain.ai.service import AiConfigService

    user = await make_user(role=UserRole.ADMINISTRADOR)
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        service = AiConfigService(session, user.tenant_id)
        await service.save(
            feature_key=FEATURE,
            model="fabricante-x/modelo-escolhido-a-mao",
            fallback_model=None,
            temperature=0.2,
            max_tokens=None,
            is_enabled=True,
            store_prompts=False,
            actor_id=user.user_id,
        )
        resolvida = await service.resolve(FEATURE)

    assert resolvida.model == "fabricante-x/modelo-escolhido-a-mao"


def test_prompt_de_sistema_cabe_no_orcamento() -> None:
    """Alvo 2: cada token de prompt de sistema é pago em TODA chamada da feature.

    O teto não é uma estética — é o que impede o prompt de virar depósito de exceção,
    crescendo um parágrafo por bug corrigido até custar mais que a pergunta do usuário.
    """
    from pathlib import Path

    from app.ai.prompts import SAFETY_RULES

    prompts = Path(__file__).resolve().parents[2] / "app" / "ai" / "prompts"
    gordos = {
        arquivo.name: len(arquivo.read_text(encoding="utf-8"))
        for arquivo in prompts.glob("*.md")
        if len(arquivo.read_text(encoding="utf-8")) > 2000
    }
    assert gordos == {}, f"prompt de sistema acima do orçamento: {gordos}"
    assert len(SAFETY_RULES) < 1200, "as regras compartilhadas entram em todo prompt"
