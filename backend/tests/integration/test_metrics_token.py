"""Spec 135, regra 4 — o token do `/metrics`, e como ele é comparado.

O `test_metrics_exige_token_quando_configurado` (spec 097) já afirma o caminho feliz:
com token configurado, sem bearer é 401 e com o bearer certo é 200. O que faltava é o
resto do espaço: um token PARECIDO, o header ausente, o esquema errado — e a forma da
comparação, que é a única coisa aqui invisível ao comportamento.
"""

import inspect

import pytest
from httpx import ASGITransport, AsyncClient

from app.core import health
from app.core.config import get_settings
from app.main import app

_TOKEN = "segredo-interno-de-32-caracteres!!"


async def _metrics(authorization: str | None) -> int:
    """Status do `/metrics` com este `Authorization`, num app com token configurado."""
    settings = get_settings()
    anterior = settings.metrics_token
    object.__setattr__(settings, "metrics_token", _TOKEN)
    try:
        async with app.router.lifespan_context(app):
            transporte = ASGITransport(app=app)
            async with AsyncClient(transport=transporte, base_url="http://test") as ac:
                headers = {"Authorization": authorization} if authorization else {}
                resposta = await ac.get("/metrics", headers=headers)
    finally:
        object.__setattr__(settings, "metrics_token", anterior)
    return resposta.status_code


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        "",
        f"Bearer {_TOKEN[:-1]}",  # quase certo, um byte a menos
        f"Bearer {_TOKEN}x",  # quase certo, um byte a mais
        _TOKEN,  # o token cru, sem o esquema
        f"bearer {_TOKEN}",  # esquema em caixa baixa — não é o mesmo header
        f"Basic {_TOKEN}",
    ],
    ids=["ausente", "vazio", "prefixo", "sufixo", "sem-esquema", "caixa-baixa", "outro-esquema"],
)
async def test_metrics_recusa_todo_authorization_que_nao_seja_exatamente_o_esperado(
    authorization: str | None,
) -> None:
    assert await _metrics(authorization) == 401


async def test_metrics_aceita_o_bearer_exato() -> None:
    assert await _metrics(f"Bearer {_TOKEN}") == 200


def test_a_comparacao_do_token_e_em_tempo_constante() -> None:
    """A única afirmação desta spec que o comportamento não consegue fazer.

    `authorization != f"Bearer {esperado}"` e `compare_digest(...)` respondem 401 nos mesmos
    casos — a diferença está no TEMPO: `!=` sai no primeiro byte diferente, e a duração da
    resposta conta quantos bytes do token o cliente já acertou. Medir tempo em teste é
    receita de suíte intermitente (o CLAUDE.md §3 proíbe até `sleep`), então o que se afirma
    aqui é a chamada: se alguém trocar `compare_digest` por `!=`, todos os testes acima
    continuam verdes e este cai.
    """
    fonte = inspect.getsource(health.prometheus_metrics)

    assert "secrets.compare_digest" in fonte
    assert "authorization !=" not in fonte
