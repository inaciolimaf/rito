from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import _auth_header
from tests.integration.test_lawsuits_listing import LawsuitFactory, _make_factory


@pytest.fixture
async def factory(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> LawsuitFactory:
    return await _make_factory(client, make_user, app_session_factory)


async def test_autocomplete_ordena_por_frequencia(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    # Regra 7: sugestões por frequência de uso, não alfabética.
    for _ in range(3):
        await factory.create(folder="Beta")
    for _ in range(2):
        await factory.create(folder="Alfa")
    await factory.create(folder="Gama")

    response = await client.get("/api/v1/lawsuits/folders", headers=factory.headers)
    assert response.status_code == 200
    assert response.json() == [
        {"name": "Beta", "count": 3},
        {"name": "Alfa", "count": 2},
        {"name": "Gama", "count": 1},
    ]


async def test_autocomplete_ignora_acento_e_caso(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    # Regra 2: comparação sem acento e sem caso; a grafia armazenada é preservada.
    await factory.create(folder="Ação Cível")

    for termo in ("acao", "AÇÃO", "civel"):
        response = await client.get(
            "/api/v1/lawsuits/folders", params={"q": termo}, headers=factory.headers
        )
        assert response.json() == [{"name": "Ação Cível", "count": 1}], f"q={termo}"


async def test_renomear_em_lote_atualiza_todos(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    # Regra 3: um único UPDATE — todos os processos da pasta mudam juntos.
    primeiro = await factory.create(folder="Velha")
    segundo = await factory.create(folder="Velha")
    await factory.create(folder="Intocada")

    # Regra 2: o `from` casa sem acento/caso ("velha" acha "Velha").
    response = await client.post(
        "/api/v1/lawsuits/folders/rename",
        json={"from": "velha", "to": "Nova"},
        headers=factory.headers,
    )
    assert response.status_code == 200
    assert response.json() == {"folder": "Nova", "updated": 2, "merged": False}

    for lawsuit_id in (primeiro, segundo):
        detail = await client.get(f"/api/v1/lawsuits/{lawsuit_id}", headers=factory.headers)
        assert detail.json()["folder"] == "Nova"

    inexistente = await client.post(
        "/api/v1/lawsuits/folders/rename",
        json={"from": "Fantasma", "to": "Nova"},
        headers=factory.headers,
    )
    assert inexistente.status_code == 404


async def test_renomear_para_existente_funde_com_confirmacao(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    await factory.create(folder="Origem")
    fundida = await factory.create(folder="Destino")

    # Regra 4: fundir exige confirmação explícita — sem `merge` é 409.
    sem_confirmar = await client.post(
        "/api/v1/lawsuits/folders/rename",
        json={"from": "Origem", "to": "destino"},
        headers=factory.headers,
    )
    assert sem_confirmar.status_code == 409
    assert "Destino" in sem_confirmar.json()["detail"]

    confirmado = await client.post(
        "/api/v1/lawsuits/folders/rename",
        json={"from": "Origem", "to": "destino", "merge": True},
        headers=factory.headers,
    )
    assert confirmado.status_code == 200
    # A grafia que prevalece é a já armazenada no alvo ("Destino", não "destino").
    assert confirmado.json() == {"folder": "Destino", "updated": 1, "merged": True}

    detail = await client.get(f"/api/v1/lawsuits/{fundida}", headers=factory.headers)
    assert detail.json()["folder"] == "Destino"


async def test_agrupamento_inclui_sem_pasta_e_ordena_por_contagem(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    # Regra 6: grupos por contagem decrescente; sem pasta cai em "Sem pasta".
    for _ in range(2):
        await factory.create(folder="Cheia")
    sem_pasta = await factory.create()

    response = await client.get(
        "/api/v1/lawsuits", params={"group_by": "folder"}, headers=factory.headers
    )
    assert response.status_code == 200
    groups = response.json()["groups"]
    assert [(group["name"], group["count"]) for group in groups] == [
        ("Cheia", 2),
        ("Sem pasta", 1),
    ]
    assert [item["id"] for item in groups[1]["items"]] == [sem_pasta]


async def test_pastas_isoladas_entre_tenants(
    client: AsyncClient,
    factory: LawsuitFactory,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    await factory.create(folder="Só do Tenant A")

    gestor_b = await make_user(role=UserRole.GESTOR)
    headers_b = _auth_header(gestor_b)
    sugestoes = await client.get("/api/v1/lawsuits/folders", headers=headers_b)
    assert sugestoes.json() == []
    grupos = await client.get("/api/v1/lawsuits", params={"group_by": "folder"}, headers=headers_b)
    assert grupos.json()["groups"] == []
