"""Spec 102, regra 15 (dívida nº 12): a busca `q` das 5 taxonomias simples (013-019)
ignora acento, como `CustomerRepository.list_filtered` já fazia desde a 019.

O sintoma que a dívida descreve: duas buscas com a mesma cara e resultados diferentes —
procurar "etica" na lista de contatos achava "Ética", e na lista de etapas não achava.
Cada caso abaixo verifica os DOIS sentidos (sem acento acha com acento, e vice-versa),
porque `unaccent` só de um lado da comparação resolveria metade do problema.
"""

import uuid
from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

from app.core.tokens import create_access_token
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


async def _criar_grupo(client: AsyncClient, headers: dict[str, str], nome: str) -> str:
    resposta = await client.post("/api/v1/action-groups", json={"name": nome}, headers=headers)
    assert resposta.status_code == 201, resposta.text
    return str(resposta.json()["id"])


@pytest.mark.parametrize(
    ("taxonomia", "rota", "criar_payload"),
    [
        ("times", "/api/v1/squads", lambda nome, _ctx: {"name": nome}),
        ("grupos de ação", "/api/v1/action-groups", lambda nome, _ctx: {"name": nome}),
        (
            "tipos de ação",
            "/api/v1/lawsuit-types",
            lambda nome, ctx: {"name": nome, "action_group_id": ctx["group_id"]},
        ),
        ("etapas", "/api/v1/stages", lambda nome, _ctx: {"name": nome, "step_id": 1}),
        ("origens", "/api/v1/customer-origins", lambda nome, _ctx: {"name": nome}),
    ],
)
async def test_busca_ignora_acento_nos_dois_sentidos(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    taxonomia: str,
    rota: str,
    criar_payload: Callable[[str, dict[str, str]], dict[str, object]],
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    ctx = {"group_id": await _criar_grupo(client, headers, f"Grupo {uuid.uuid4().hex[:8]}")}

    # Um registro COM acento e outro SEM, com radicais distintos, para provar os dois
    # sentidos sem que um ache o outro por coincidência.
    com_acento = f"Ética {uuid.uuid4().hex[:6]}"
    sem_acento = f"Consorcio {uuid.uuid4().hex[:6]}"
    for nome in (com_acento, sem_acento):
        criado = await client.post(rota, json=criar_payload(nome, ctx), headers=headers)
        assert criado.status_code == 201, f"{taxonomia}: {criado.text}"

    # Buscar SEM acento acha o registro COM acento.
    sem = await client.get(rota, params={"q": "etica"}, headers=headers)
    assert sem.status_code == 200
    nomes_sem = [item["name"] for item in sem.json()["items"]]
    assert com_acento in nomes_sem, f"{taxonomia}: buscar 'etica' não achou {com_acento!r}"

    # Buscar COM acento acha o registro SEM acento.
    com = await client.get(rota, params={"q": "consórcio"}, headers=headers)
    assert com.status_code == 200
    nomes_com = [item["name"] for item in com.json()["items"]]
    assert sem_acento in nomes_com, f"{taxonomia}: buscar 'consórcio' não achou {sem_acento!r}"

    # E continua sendo busca, não "devolve tudo": o outro registro fica de fora.
    assert sem_acento not in nomes_sem
    assert com_acento not in nomes_com
