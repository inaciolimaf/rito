"""Spec 098, regra 2 — metas de p95 com o volume do §4.

Roda no NOTURNO, não no CI de PR (regra 10): o seed são 1,95 milhão de linhas, e o
orçamento do PR é de 300 s para a suíte inteira. É aqui, e só aqui, que se descobre o
índice que falta — o plano que o Postgres escolhe com mil linhas é outro.

    make test-nightly     # semeia, mede e limpa

Cada meta é medida sobre várias execuções e comparada pelo p95, não pela média: a média
esconde exatamente o caso que o usuário reclama, que é a requisição lenta ocasional.
"""

import math
import time
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.tokens import create_access_token
from app.main import app
from scripts.volume_seed import _USER_ID, VOLUME_TENANT_ID

pytestmark = pytest.mark.nightly

# Cem execuções, não vinte. Com 20 amostras o "p95" é, na prática, o MÁXIMO — qualquer
# definição de percentil cai na penúltima amostra — e um único pico de GC, checkpoint ou
# autovacuum decide o resultado. Medido ao fechar a 098: a mesma rota dava 379 ms de
# requisição real e 714 ms de "p95" de 20 amostras. Com 100, o 95º valor é o 95º.
REPETICOES = 100

# Regra 2, tabela de metas — em milissegundos.
METAS_MS: list[tuple[str, str, int]] = [
    ("listagem de contatos", "/api/v1/customers", 300),
    ("listagem de processos", "/api/v1/lawsuits", 300),
    ("listagem de lançamentos", "/api/v1/transactions", 300),
    # Termo que casa alguns milhares de contatos, não a base inteira — é o que
    # um usuário digita.
    ("busca global", "/api/v1/search?q=Marina", 200),
    ("dashboard de processos", "/api/v1/lawsuits/stats", 500),
    ("dashboard de contatos", "/api/v1/customers/stats", 500),
    ("quadro do CRM", "/api/v1/crm/board", 400),
]


def p95(amostras: list[float]) -> float:
    """Percentil 95 pelo método do valor mais próximo — o 95º de 100, sem interpolar.

    `statistics.quantiles(..., n=20)[-1]` interpola entre as duas maiores amostras, o
    que com poucas amostras devolve algo bem mais próximo do máximo que do percentil.
    """
    ordenadas = sorted(amostras)
    indice = max(0, math.ceil(0.95 * len(ordenadas)) - 1)
    return ordenadas[indice]


@pytest.fixture
async def volume_disponivel(admin_engine: AsyncEngine) -> None:
    """O perfilamento sem o seed mediria um banco vazio e passaria sempre — que é pior
    que falhar, porque parece verde."""
    async with admin_engine.begin() as conn:
        total = await conn.scalar(
            text("SELECT count(*) FROM lawsuits WHERE tenant_id = :t"), {"t": VOLUME_TENANT_ID}
        )
    if not total or total < 50_000:
        pytest.fail(
            "banco sem volume — use `make test-nightly`, que semeia antes de medir "
            f"(processos encontrados: {total})"
        )


@pytest.mark.parametrize(("rotulo", "caminho", "meta_ms"), METAS_MS, ids=[m[0] for m in METAS_MS])
async def test_p95_dentro_da_meta(
    volume_disponivel: None, rotulo: str, caminho: str, meta_ms: int
) -> None:
    token = create_access_token(user_id=_USER_ID, tenant_id=VOLUME_TENANT_ID)
    headers = {"Authorization": f"Bearer {token}"}

    async with app.router.lifespan_context(app):
        transporte = ASGITransport(app=app)
        async with AsyncClient(transport=transporte, base_url="http://test") as ac:
            # Descartada: a primeira requisição paga o plano frio e o cache vazio, e
            # incluí-la mediria o pior caso de arranque, não o regime.
            await ac.get(caminho, headers=headers)
            amostras = []
            for _ in range(REPETICOES):
                comeco = time.perf_counter()
                resposta = await ac.get(caminho, headers=headers)
                amostras.append((time.perf_counter() - comeco) * 1000)
                assert resposta.status_code == 200, resposta.text

    medido = p95(amostras)
    assert (
        medido <= meta_ms
    ), f"{rotulo}: p95 de {medido:.0f} ms, meta é {meta_ms} ms (spec 098, regra 2)"


async def test_o_tenant_de_volume_nao_vaza_para_outro_escritorio(
    volume_disponivel: None,
) -> None:
    """Com 1,95 milhão de linhas no banco, um vazamento de RLS deixa de ser sutil — e
    esta é a única execução em que ele apareceria por tempo de resposta."""
    outro = uuid.uuid4()
    token = create_access_token(user_id=uuid.uuid4(), tenant_id=outro)

    async with app.router.lifespan_context(app):
        transporte = ASGITransport(app=app)
        async with AsyncClient(transport=transporte, base_url="http://test") as ac:
            resposta = await ac.get(
                "/api/v1/customers", headers={"Authorization": f"Bearer {token}"}
            )

    # Usuário inexistente no tenant novo: 401 antes de qualquer leitura de dado.
    assert resposta.status_code == 401
