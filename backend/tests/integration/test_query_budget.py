"""Spec 098, regras 1 e 11 — o gate de performance que roda em TODO PR.

Não mede tempo, mede **queries**. Tempo em CI compartilhado oscila 30% entre execuções e
transformaria o gate num gerador de falso vermelho; contagem de queries é determinística
e pega exatamente a regressão que interessa — o N+1 que alguém acabou de introduzir.

Os orçamentos são os da tabela da regra 1 e incluem a query de autenticação: toda rota
autenticada carrega o usuário do token, e uma listagem cabe em 3 justamente porque são
`usuário + página + total`. O que NÃO conta é o `SELECT set_config('app.tenant_id')` do
preâmbulo de RLS — plumbing de sessão, não acesso a dado (ver `tests/perf.py`).
"""

import uuid
from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

from app.domain.users.models import FinancialAccess, UserRole
from app.main import app
from tests.integration.conftest import SeededUser, auth_header
from tests.integration.test_lawsuits import (
    _create_customer,
    _create_lawsuit,
    _create_lawsuit_type,
    _create_stage,
)
from tests.perf import query_budget

# (rótulo, caminho, orçamento) — a tabela da regra 1, endpoint a endpoint.
# `{lawsuit}` e `{customer}` são preenchidos com os ids do cenário montado abaixo.
ORCAMENTOS: list[tuple[str, str, int]] = [
    # Listagens: usuário + página + total.
    ("listagem de contatos", "/api/v1/customers", 3),
    ("listagem de processos", "/api/v1/lawsuits", 3),
    ("listagem de tarefas", "/api/v1/lawsuits/{lawsuit}/posts", 3),
    ("listagem de lançamentos", "/api/v1/transactions", 3),
    ("listagem de notificações", "/api/v1/notifications", 3),
    # Detalhe com relações.
    ("detalhe de contato", "/api/v1/customers/{customer}", 5),
    ("detalhe de processo", "/api/v1/lawsuits/{lawsuit}", 5),
    # Dashboards.
    ("dashboard de processos", "/api/v1/lawsuits/stats", 5),
    ("dashboard de contatos", "/api/v1/customers/stats", 5),
    ("dashboard financeiro", "/api/v1/transactions/stats", 5),
    ("quadro do CRM", "/api/v1/crm/board", 5),
    # Timeline e busca têm orçamento próprio na regra 1.
    ("timeline do processo", "/api/v1/lawsuits/{lawsuit}/timeline", 3),
    ("busca global", "/api/v1/search?q=Cliente", 4),
]


@pytest.fixture
async def cenario(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> tuple[dict[str, str], uuid.UUID, uuid.UUID]:
    """Escritório com um processo e um cliente — o mínimo para as 13 rotas responderem
    200. O orçamento é sobre a FORMA da query, não sobre o volume: um endpoint que faz
    duas queries com uma linha faz duas com um milhão."""
    user = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    headers = auth_header(user)
    type_id, _grupo = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    customer_id = await _create_customer(client, headers, "Cliente Um")
    lawsuit = await _create_lawsuit(
        client,
        headers,
        user_id=str(user.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        folder="ORC-1",
        parties=[{"customer_id": customer_id, "pole": "ATIVO", "is_client": True}],
    )
    return headers, uuid.UUID(str(lawsuit["id"])), uuid.UUID(customer_id)


@pytest.mark.parametrize(
    ("rotulo", "caminho", "maximo"), ORCAMENTOS, ids=[o[0] for o in ORCAMENTOS]
)
async def test_endpoint_dentro_do_orcamento_de_queries(
    client: AsyncClient,
    cenario: tuple[dict[str, str], uuid.UUID, uuid.UUID],
    rotulo: str,
    caminho: str,
    maximo: int,
) -> None:
    headers, lawsuit_id, customer_id = cenario
    url = caminho.format(lawsuit=lawsuit_id, customer=customer_id)

    async with query_budget(app, maximo, label=rotulo):
        resposta = await client.get(url, headers=headers)

    assert resposta.status_code == 200, resposta.text
