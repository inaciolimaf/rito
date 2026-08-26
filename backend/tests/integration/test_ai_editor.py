"""IA no editor (spec 088).

O que se verifica aqui é a fronteira entre ajudar e escrever no lugar: a revisão aponta
e não toca no documento, a reescrita devolve só o trecho, o contexto enviado é recortado
e a fundamentação passa pelo mesmo guarda-corpo de citação da 087.
"""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.ai.editor import CONTEXT_AFTER_LIMIT, CONTEXT_BEFORE_LIMIT, MAX_SELECTION
from app.domain.ai.models import EditorAiAction
from app.domain.legal_agents.citations import REMOVED_MARKER
from app.domain.templates.models import Template
from app.domain.users.models import UserRole
from app.integrations.openrouter.types import LLMChunk, LLMResponse, Message, Usage
from tests.integration.conftest import SeededUser, auth_header
from tests.integration.test_ai_copilot import ScriptedProvider, _use
from tests.integration.test_lawsuits import (
    _auth_header,
    _create_customer,
    _create_lawsuit,
    _create_lawsuit_type,
    _create_stage,
)


class StreamingProvider(ScriptedProvider):
    """Provider que devolve a resposta em pedaços — é o caminho de streaming real da
    081, exercitado sem rede."""

    def __init__(self, *, pieces: Sequence[str], answer: str | None = None) -> None:
        super().__init__(
            script=(
                [
                    LLMResponse(
                        content=answer or "".join(pieces),
                        usage=Usage(prompt_tokens=100, completion_tokens=50),
                        model="fabricante-x/modelo-y",
                        finish_reason="stop",
                    )
                ]
                if answer is not None
                else []
            )
        )
        self.pieces = list(pieces)
        self.stream_prompts: list[list[Message]] = []

    async def stream(self, **kwargs: Any) -> AsyncIterator[LLMChunk]:
        self.stream_prompts.append(list(kwargs.get("messages") or []))
        self.models_used.append(str(kwargs.get("model")))
        for piece in self.pieces:
            yield LLMChunk(kind="chunk", content=piece)
        yield LLMChunk(kind="done", finish_reason="stop")


async def _sse(client: AsyncClient, user: SeededUser, path: str, payload: dict[str, Any]) -> str:
    async with client.stream(
        "POST", f"/api/v1/ai/editor/{path}", json=payload, headers=auth_header(user)
    ) as stream:
        return "".join([chunk async for chunk in stream.aiter_text()])


async def _template(client: AsyncClient, user: SeededUser, content: str) -> str:
    resposta = await client.post(
        "/api/v1/templates",
        json={"name": f"Peça {uuid.uuid4().hex[:6]}", "type": "PETICAO", "content": content},
        headers=auth_header(user),
    )
    assert resposta.status_code == 201, resposta.text
    return str(resposta.json()["id"])


@pytest.fixture(autouse=True)
def _reset_overrides() -> Any:
    from app.domain.ai.router import get_llm_provider
    from app.main import app

    yield
    app.dependency_overrides.pop(get_llm_provider, None)


async def test_continuar_gera_a_partir_do_contexto_em_streaming(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 2: o texto chega em pedaços, para a pessoa ver a frase se formar."""
    user = await make_user()
    provider = StreamingProvider(pieces=["Diante do exposto, ", "requer a procedência."])
    _use(provider)

    eventos = await _sse(
        client,
        user,
        "continue",
        {"context_before": "<p>O autor demonstrou o dano moral sofrido.</p>"},
    )

    assert eventos.count("event: chunk") == 2
    assert "requer a procedência." in eventos
    assert "event: done" in eventos
    assert "dano moral" in provider.stream_prompts[0][-1].content

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        registro = (await session.scalars(select(EditorAiAction))).one()
    assert registro.action == "continue"
    assert registro.output == "Diante do exposto, requer a procedência."
    assert registro.accepted is None, "só vira booleano quando a pessoa decide"


async def test_reescrita_pede_apenas_o_trecho(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 3: a saída substitui só a seleção — o prompt proíbe devolver o entorno."""
    user = await make_user()
    provider = StreamingProvider(pieces=["Trecho reescrito."])
    _use(provider)

    await _sse(
        client,
        user,
        "rewrite",
        {"selection": "texto original", "instruction": "deixe mais direto"},
    )

    prompt = provider.stream_prompts[0][-1].content
    assert "APENAS o trecho" in prompt
    assert "sem repetir o texto em volta" in prompt
    assert "deixe mais direto" in prompt


async def test_os_quatro_tons_mandam_instrucoes_diferentes(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 4: quatro tons, quatro instruções — se fossem a mesma, o seletor seria
    enfeite."""
    user = await make_user()
    provider = StreamingProvider(pieces=["saída"])
    _use(provider)

    for tone in ("formal", "objetivo", "tecnico", "simples"):
        await _sse(client, user, "tone", {"selection": "um trecho", "tone": tone})

    instrucoes = {prompt[-1].content for prompt in provider.stream_prompts}
    assert len(instrucoes) == 4

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        registros = list((await session.scalars(select(EditorAiAction))).all())
    assert {registro.instruction for registro in registros} == {
        "formal",
        "objetivo",
        "tecnico",
        "simples",
    }


async def test_revisao_devolve_checklist_estruturado_e_nao_altera_o_documento(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regras 5 e 6 — a segunda é o teste que a spec marca: apontar, não corrigir."""
    user = await make_user()
    conteudo = "<h1>PETIÇÃO</h1><p>Dos fatos.</p>"
    template_id = await _template(client, user, conteudo)
    _use(
        ScriptedProvider(
            script=[
                LLMResponse(
                    content=(
                        '{"items": [{"topic": "estrutura", "status": "ok", "note": "Tem '
                        'endereçamento e pedidos."}, {"topic": "pedidos", "status": '
                        '"problema", "note": "Falta o pedido de justiça gratuita."}]}'
                    ),
                    usage=Usage(prompt_tokens=300, completion_tokens=90),
                    model="fabricante-x/modelo-y",
                    finish_reason="stop",
                )
            ]
        )
    )

    resposta = await client.post(
        "/api/v1/ai/editor/review",
        json={"template_id": template_id},
        headers=auth_header(user),
    )

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["document_changed"] is False
    itens = {item["topic"]: item for item in corpo["items"]}
    # Regra 5: os cinco eixos sempre presentes — quatro itens pareceriam revisão completa.
    assert set(itens) == {"estrutura", "fundamentacao", "pedidos", "coerencia", "linguagem"}
    assert itens["pedidos"]["status"] == "problema"
    assert itens["fundamentacao"]["status"] == "nao_avaliado"

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        template = await session.get(Template, uuid.UUID(template_id))
    assert template is not None and template.content == conteudo


async def test_fundamentacao_nao_inventa_citacao(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 7: mesmo guarda-corpo da 087 — a tentação de inventar súmula é a mesma."""
    user = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(user)
    type_id, _group = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    customer_id = await _create_customer(client, headers, "Cliente do Caso")
    lawsuit = await _create_lawsuit(
        client,
        headers,
        user_id=str(user.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        parties=[{"customer_id": customer_id, "pole": "ATIVO", "is_client": True}],
    )
    _use(
        ScriptedProvider(
            script=[
                LLMResponse(
                    content="<p>Aplica-se a Súmula 331 do TST ao caso.</p>",
                    usage=Usage(prompt_tokens=200, completion_tokens=40),
                    model="fabricante-x/modelo-y",
                    finish_reason="stop",
                )
            ]
        )
    )

    resposta = await client.post(
        "/api/v1/ai/editor/ground",
        json={"selection": "O vínculo é reconhecido.", "lawsuit_id": str(lawsuit["id"])},
        headers=auth_header(user),
    )

    assert resposta.status_code == 200, resposta.text
    assert "Súmula 331" not in resposta.json()["output"]
    assert REMOVED_MARKER in resposta.json()["output"]
    assert resposta.json()["warnings"][0]["kind"] == "súmula"


async def test_contexto_enviado_respeita_o_limite(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 8: prompt maior é conta maior — e o modelo não escreve melhor com o
    documento inteiro do que com o parágrafo certo."""
    user = await make_user()
    provider = StreamingProvider(pieces=["ok"])
    _use(provider)

    await _sse(
        client,
        user,
        "continue",
        {
            "context_before": "A" * (CONTEXT_BEFORE_LIMIT + 500),
            "context_after": "B" * (CONTEXT_AFTER_LIMIT + 500),
        },
    )

    prompt = provider.stream_prompts[0][-1].content
    # Comparação por sequência (e não por contagem de letra): o próprio texto do prompt
    # tem "A" e "B" soltos, e contá-los mediria a instrução, não o recorte.
    assert "A" * CONTEXT_BEFORE_LIMIT in prompt
    assert "A" * (CONTEXT_BEFORE_LIMIT + 1) not in prompt
    assert "B" * CONTEXT_AFTER_LIMIT in prompt
    assert "B" * (CONTEXT_AFTER_LIMIT + 1) not in prompt


async def test_selecao_gigante_e_recusada_com_explicacao(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 9."""
    user = await make_user()
    _use(StreamingProvider(pieces=["ok"]))

    resposta = await client.post(
        "/api/v1/ai/editor/rewrite",
        json={"selection": "x" * (MAX_SELECTION + 1), "instruction": "melhore"},
        headers=auth_header(user),
    )

    assert resposta.status_code == 422
    assert "trecho menor" in resposta.json()["detail"]


async def test_feedback_grava_aceite_e_descarte(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 10: é essa proporção que diz se a feature está ajudando."""
    user = await make_user()
    _use(StreamingProvider(pieces=["sugestão"]))
    eventos = await _sse(client, user, "continue", {"context_before": "<p>Texto.</p>"})
    action_id = eventos.split('"action_id": "')[1].split('"')[0]

    resposta = await client.post(
        f"/api/v1/ai/editor/actions/{action_id}/feedback",
        json={"accepted": False},
        headers=auth_header(user),
    )

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["accepted"] is False
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        registro = (await session.scalars(select(EditorAiAction))).one()
    assert registro.accepted is False


async def test_sem_chave_a_assistencia_avisa_em_vez_de_quebrar(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 11: o cliente recebe erro claro (e esconde o menu) em vez de um stream que
    morre no meio."""
    user = await make_user()

    class SemChave(ScriptedProvider):
        def __init__(self) -> None:
            super().__init__()
            self.is_configured = False

        async def stream(self, **kwargs: Any) -> AsyncIterator[LLMChunk]:
            from app.integrations.openrouter.types import LLMNotConfiguredError

            raise LLMNotConfiguredError("sem chave")
            yield LLMChunk(kind="done")  # pragma: no cover

    _use(SemChave())

    eventos = await _sse(client, user, "continue", {"context_before": "<p>Texto.</p>"})

    assert "event: error" in eventos
    assert "não está disponível" in eventos
