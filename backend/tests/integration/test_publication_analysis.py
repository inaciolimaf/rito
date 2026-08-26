"""IA em intimações (spec 086).

A regra que o teste persegue é a 1: **prazo sugerido não é prazo do escritório**. Tudo
o que a IA produz aqui fica em `publication_analyses` até alguém confirmar — e é a
confirmação que cria a tarefa com a data.
"""

import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import date
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.posts.models import Post
from app.domain.publications.analysis import (
    FALLBACK_TASK_TYPE_NAME,
    PublicationAnalysisService,
    parse_model_output,
)
from app.domain.publications.analysis_models import PublicationAnalysis
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser, auth_header
from tests.integration.test_ai_copilot import ScriptedProvider, _use
from tests.integration.test_lawsuits import (
    _auth_header,
    _create_lawsuit,
    _create_lawsuit_type,
    _create_stage,
)
from tests.integration.test_publications_listing import make_publication

TODAY = date(2026, 8, 5)  # quarta-feira


def _model_answer(payload: dict[str, Any]) -> Any:
    import json

    from app.integrations.openrouter.types import LLMResponse, Usage

    return LLMResponse(
        content=json.dumps(payload, ensure_ascii=False),
        usage=Usage(prompt_tokens=500, completion_tokens=120),
        model="fabricante-x/modelo-y",
        finish_reason="stop",
    )


_DEFAULT_PAYLOAD = {
    "summary": "Intimação para apresentar contestação no processo.",
    "act_type": "intimacao_prazo",
    "requires_action": True,
    "deadline_days": 15,
    "deadline_kind": "uteis",
    "confidence": 0.93,
    "reasoning": "O texto diz 'prazo de 15 dias úteis para contestar'.",
}


async def _create_task_type(client: AsyncClient, headers: dict[str, str], name: str) -> str:
    response = await client.post(
        "/api/v1/task-types",
        json={"name": name, "complexity": "SIMPLES", "duration": "MIN_15", "reward": 5},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def _setup(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    sessions: async_sessionmaker[AsyncSession],
    *,
    task_type_names: Sequence[str] = ("Contestação", FALLBACK_TASK_TYPE_NAME),
) -> tuple[SeededUser, uuid.UUID, str]:
    """Escritório com processo, catálogo de tarefas e uma intimação vinculada."""
    user = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(user)
    type_id, _group = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    lawsuit = await _create_lawsuit(
        client, headers, user_id=str(user.user_id), lawsuit_type_id=type_id, stage_id=stage_id
    )
    for nome in task_type_names:
        await _create_task_type(client, headers, nome)
    publication_id = await make_publication(
        sessions,
        user.tenant_id,
        availability_date=TODAY,
        lawsuit_id=uuid.UUID(str(lawsuit["id"])),
        routed_to=user.user_id,
    )
    return user, publication_id, str(lawsuit["id"])


async def _analysis(
    sessions: async_sessionmaker[AsyncSession], user: SeededUser
) -> PublicationAnalysis:
    async with sessions() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        return (await session.scalars(select(PublicationAnalysis))).one()


def test_saida_ilegivel_do_modelo_nao_derruba_a_analise() -> None:
    """O pior caso aceitável é uma análise sem prazo (regra 5), nunca uma intimação que
    some da fila porque o parser quebrou."""
    parsed = parse_model_output("desculpe, não consegui")

    assert parsed.deadline_days is None
    assert parsed.summary


def test_json_embrulhado_em_markdown_ainda_e_lido() -> None:
    parsed = parse_model_output(
        '```json\n{"summary": "ok", "deadline_days": 5, ' '"deadline_kind": "uteis"}\n```'
    )

    assert parsed.summary == "ok"
    assert parsed.deadline_days == 5


async def test_analise_gera_resumo_tipo_e_prazo_calculado(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """O modelo lê e diz "15 dias úteis"; quem conta os dias é o código."""
    user, publication_id, _lawsuit = await _setup(client, make_user, app_session_factory)
    _use(ScriptedProvider(script=[_model_answer(_DEFAULT_PAYLOAD)]))

    resposta = await client.post(
        f"/api/v1/publications/{publication_id}/analyze", headers=auth_header(user)
    )

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["act_type"] == "intimacao_prazo"
    assert corpo["deadline_days"] == 15
    # 5/8/2026 (quarta) + 15 dias úteis = 26/8/2026.
    assert corpo["deadline_date"] == "2026-08-26"
    assert corpo["deadline_confidence"] == 0.93
    assert corpo["should_prefill_deadline"] is True
    assert "15 dias úteis" in corpo["reasoning"]
    assert corpo["reviewed_at"] is None


async def test_prazo_nao_vira_tarefa_sem_revisao_humana(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 1 — o teste central da spec: analisar não cria prazo nenhum."""
    user, publication_id, _lawsuit = await _setup(client, make_user, app_session_factory)
    _use(ScriptedProvider(script=[_model_answer(_DEFAULT_PAYLOAD)]))

    await client.post(f"/api/v1/publications/{publication_id}/analyze", headers=auth_header(user))

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        tarefas = list((await session.scalars(select(Post))).all())
    assert tarefas == [], "análise não pode criar tarefa — só a revisão humana cria"


async def test_revisao_humana_aplica_o_prazo_na_tarefa(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 1, segunda metade: confirmado, vira tarefa com data — e fica registrado
    quem confirmou."""
    user, publication_id, lawsuit_id = await _setup(client, make_user, app_session_factory)
    _use(ScriptedProvider(script=[_model_answer(_DEFAULT_PAYLOAD)]))
    await client.post(f"/api/v1/publications/{publication_id}/analyze", headers=auth_header(user))

    revisao = await client.post(
        f"/api/v1/publications/{publication_id}/analysis/review",
        json={"approved": True},
        headers=auth_header(user),
    )

    assert revisao.status_code == 200, revisao.text
    assert revisao.json()["post_id"] is not None
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        tarefa = (await session.scalars(select(Post))).one()
        analise = (await session.scalars(select(PublicationAnalysis))).one()
    assert tarefa.deadline_date == date(2026, 8, 26)
    assert str(tarefa.lawsuit_id) == lawsuit_id
    assert analise.reviewed_by == user.user_id
    assert analise.reviewed_at is not None
    # Regra 11: sem correção significa "a IA acertou" — e isso também é dado.
    assert analise.human_correction == {}


async def test_confianca_baixa_nao_pre_preenche(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 4: mostra o número, não preenche o campo."""
    user, publication_id, _lawsuit = await _setup(client, make_user, app_session_factory)
    _use(ScriptedProvider(script=[_model_answer({**_DEFAULT_PAYLOAD, "confidence": 0.55})]))

    resposta = await client.post(
        f"/api/v1/publications/{publication_id}/analyze", headers=auth_header(user)
    )

    corpo = resposta.json()
    assert corpo["deadline_date"] == "2026-08-26"  # a conta é feita
    assert corpo["should_prefill_deadline"] is False  # mas o campo não nasce preenchido


async def test_sem_prazo_identificado_nao_sugere_data(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 5: não inventar prazo é mais importante do que sempre ter resposta."""
    user, publication_id, _lawsuit = await _setup(client, make_user, app_session_factory)
    _use(
        ScriptedProvider(
            script=[
                _model_answer(
                    {
                        "summary": "Mero despacho de expediente.",
                        "act_type": "despacho",
                        "requires_action": False,
                        "deadline_days": None,
                        "deadline_kind": None,
                        "confidence": 0.9,
                        "reasoning": "Não há prazo no texto.",
                    }
                )
            ]
        )
    )

    corpo = (
        await client.post(
            f"/api/v1/publications/{publication_id}/analyze", headers=auth_header(user)
        )
    ).json()

    assert corpo["requires_action"] is False
    assert corpo["deadline_date"] is None
    assert corpo["should_prefill_deadline"] is False


async def test_sugestao_de_tarefa_casa_com_o_catalogo_do_escritorio(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 8."""
    user, publication_id, _lawsuit = await _setup(client, make_user, app_session_factory)
    _use(ScriptedProvider(script=[_model_answer(_DEFAULT_PAYLOAD)]))

    corpo = (
        await client.post(
            f"/api/v1/publications/{publication_id}/analyze", headers=auth_header(user)
        )
    ).json()

    tipos = await client.get("/api/v1/task-types", headers=auth_header(user))
    contestacao = next(item for item in tipos.json()["items"] if item["name"] == "Contestação")
    assert corpo["suggested_task_type_id"] == contestacao["id"]
    # Regra 9: o responsável vem das rotas da 045, já resolvidas na intimação.
    assert corpo["suggested_user_id"] == str(user.user_id)


async def test_sem_correspondencia_sugere_analisar_intimacao(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 8: sem tipo correspondente, o fallback explícito — nunca um tipo
    "parecido", que mandaria a tarefa para a fila errada."""
    user, publication_id, _lawsuit = await _setup(
        client,
        make_user,
        app_session_factory,
        task_type_names=("Petição inicial", FALLBACK_TASK_TYPE_NAME),
    )
    _use(ScriptedProvider(script=[_model_answer({**_DEFAULT_PAYLOAD, "act_type": "pericia"})]))

    corpo = (
        await client.post(
            f"/api/v1/publications/{publication_id}/analyze", headers=auth_header(user)
        )
    ).json()

    tipos = await client.get("/api/v1/task-types", headers=auth_header(user))
    fallback = next(
        item for item in tipos.json()["items"] if item["name"] == FALLBACK_TASK_TYPE_NAME
    )
    assert corpo["suggested_task_type_id"] == fallback["id"]


async def test_correcao_humana_e_gravada(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 11: é a única forma honesta de medir se o modelo está melhorando."""
    user, publication_id, _lawsuit = await _setup(client, make_user, app_session_factory)
    _use(ScriptedProvider(script=[_model_answer(_DEFAULT_PAYLOAD)]))
    await client.post(f"/api/v1/publications/{publication_id}/analyze", headers=auth_header(user))

    corrigido = date(2026, 8, 20)
    await client.post(
        f"/api/v1/publications/{publication_id}/analysis/review",
        json={"approved": True, "deadline_date": corrigido.isoformat()},
        headers=auth_header(user),
    )

    analise = await _analysis(app_session_factory, user)
    assert analise.human_correction == {
        "deadline_date": {"suggested": "2026-08-26", "corrected": "2026-08-20"}
    }
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        tarefa = (await session.scalars(select(Post))).one()
    assert tarefa.deadline_date == corrigido, "vale a data do humano, não a da IA"


async def test_reanalise_preserva_o_historico_de_correcoes(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 13."""
    user, publication_id, _lawsuit = await _setup(client, make_user, app_session_factory)
    _use(ScriptedProvider(script=[_model_answer(_DEFAULT_PAYLOAD)]))
    await client.post(f"/api/v1/publications/{publication_id}/analyze", headers=auth_header(user))
    await client.post(
        f"/api/v1/publications/{publication_id}/analysis/review",
        json={"approved": True, "deadline_date": "2026-08-20"},
        headers=auth_header(user),
    )

    _use(ScriptedProvider(script=[_model_answer({**_DEFAULT_PAYLOAD, "deadline_days": 5})]))
    nova = await client.post(
        f"/api/v1/publications/{publication_id}/analyze", headers=auth_header(user)
    )

    assert nova.json()["deadline_days"] == 5
    assert nova.json()["reviewed_at"] is None, "a reanálise volta a esperar revisão"
    analise = await _analysis(app_session_factory, user)
    assert len(analise.previous_corrections) == 1
    assert analise.previous_corrections[0]["correction"]["deadline_date"]["corrected"] == (
        "2026-08-20"
    )


async def test_leitura_automatica_processa_em_background(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 10: desligada por padrão; ligada, a varredura analisa o que chegou."""
    user, publication_id, _lawsuit = await _setup(client, make_user, app_session_factory)
    provider = ScriptedProvider(script=[_model_answer(_DEFAULT_PAYLOAD)])

    async def _varrer() -> int:
        async with app_session_factory() as session, session.begin():
            await set_tenant_context(session, user.tenant_id)
            service = PublicationAnalysisService(
                session=session,
                tenant_id=user.tenant_id,
                runner=_runner(session, user.tenant_id, provider),
            )
            if not await service.auto_read_enabled():
                return 0
            pendentes = await service.analyses.publications_without_analysis(10)
            for publication in pendentes:
                await service.analyze(publication)
            return len(pendentes)

    assert await _varrer() == 0, "o padrão é desligado — ninguém gasta token sem pedir"

    # A opção mora na conta do escritório (spec 011), então ela precisa existir.
    from tests.integration.test_account import _valid_payload

    criada = await client.put("/api/v1/account", json=_valid_payload(), headers=auth_header(user))
    assert criada.status_code in (200, 201), criada.text

    ligado = await client.put(
        "/api/v1/account/ai-settings",
        json={"ai_auto_read_publications": True},
        headers=auth_header(user),
    )
    assert ligado.status_code == 200, ligado.text

    assert await _varrer() == 1
    analise = await _analysis(app_session_factory, user)
    assert analise.publication_id == publication_id


def _runner(session: AsyncSession, tenant_id: uuid.UUID, provider: Any) -> Any:
    from app.domain.ai.service import AiRunner

    return AiRunner(session, tenant_id, provider)


async def test_estimativa_de_custo_antes_de_analisar_o_lote(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 12: "analisar todas" mostra o tamanho da conta antes de gastar."""
    user, _publication_id, _lawsuit = await _setup(client, make_user, app_session_factory)
    _use(ScriptedProvider())

    resposta = await client.get("/api/v1/publications/analysis/estimate", headers=auth_header(user))

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["count"] == 1
    assert resposta.json()["estimated_prompt_tokens"] > 0


async def test_prazo_atravessa_feriado_nacional_cadastrado(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
    admin_engine: Any,
) -> None:
    """O cálculo usa os feriados REAIS do banco (spec 038), não uma lista no código."""
    user, publication_id, _lawsuit = await _setup(client, make_user, app_session_factory)
    async with admin_engine.begin() as conn:
        from sqlalchemy import text as sql_text

        await conn.execute(
            sql_text(
                "INSERT INTO holidays (date, name, is_national) "
                "VALUES (:day, 'Feriado de teste', true) ON CONFLICT DO NOTHING"
            ),
            {"day": date(2026, 8, 12)},
        )
    _use(ScriptedProvider(script=[_model_answer({**_DEFAULT_PAYLOAD, "deadline_days": 5})]))

    corpo = (
        await client.post(
            f"/api/v1/publications/{publication_id}/analyze", headers=auth_header(user)
        )
    ).json()

    # 5 dias úteis a partir de 5/8 seriam 12/8; com o feriado, escorrega para 13/8.
    assert corpo["deadline_date"] == "2026-08-13"

    async with admin_engine.begin() as conn:
        from sqlalchemy import text as sql_text

        await conn.execute(
            sql_text("DELETE FROM holidays WHERE date = :day"), {"day": date(2026, 8, 12)}
        )


@pytest.fixture(autouse=True)
def _reset_overrides() -> Any:
    from app.domain.ai.router import get_llm_provider
    from app.main import app

    yield
    app.dependency_overrides.pop(get_llm_provider, None)
