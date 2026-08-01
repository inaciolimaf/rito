import uuid
from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.core.tokens import create_access_token
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser

# Fase 1 = Marketing, fase 2 = Negociação (seed da migration 015) — usadas nos testes que
# só precisam de uma fase válida qualquer.
_MARKETING_STEP_ID = 1
_NEGOCIACAO_STEP_ID = 2


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


async def _create_stage(
    client: AsyncClient, headers: dict[str, str], name: str, step_id: int = _MARKETING_STEP_ID
) -> str:
    response = await client.post(
        "/api/v1/stages", json={"name": name, "step_id": step_id}, headers=headers
    )
    assert response.status_code == 201
    result: str = response.json()["id"]
    return result


async def test_fases_sao_somente_leitura_405(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)

    list_response = await client.get("/api/v1/steps", headers=headers)
    assert list_response.status_code == 200
    names = [item["name"] for item in list_response.json()]
    assert names == [
        "Marketing",
        "Negociação",
        "Consultoria",
        "Administrativo",
        "Judicial",
        "Recursal",
        "Execução/cobrança",
        "Rh/financeiro",
        "Arquivamento",
    ]

    post_response = await client.post("/api/v1/steps", json={"name": "Nova Fase"}, headers=headers)
    assert post_response.status_code == 405


async def test_crud_de_etapas(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)

    stage_id = await _create_stage(client, headers, "Fazendo Contato", _NEGOCIACAO_STEP_ID)

    get_response = await client.get("/api/v1/stages", headers=headers)
    assert get_response.status_code == 200
    item = next(row for row in get_response.json()["items"] if row["id"] == stage_id)
    assert item["step_name"] == "Negociação"

    update_response = await client.put(
        f"/api/v1/stages/{stage_id}",
        json={"name": "Contato Feito", "step_id": _NEGOCIACAO_STEP_ID, "is_active": True},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Contato Feito"

    delete_response = await client.delete(f"/api/v1/stages/{stage_id}", headers=headers)
    assert delete_response.status_code == 204


async def test_estagnacao_sem_dias_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)

    response = await client.post(
        "/api/v1/stages",
        json={
            "name": "Estagnação Sem Dias",
            "step_id": _MARKETING_STEP_ID,
            "enable_stagnant_days": True,
        },
        headers=headers,
    )

    assert response.status_code == 422


async def test_mudar_etapa_de_fase_reposiciona_no_fim_da_nova_fase(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    await _create_stage(client, headers, "Já Na Negociação", _NEGOCIACAO_STEP_ID)
    stage_id = await _create_stage(client, headers, "Muda De Fase", _MARKETING_STEP_ID)

    response = await client.put(
        f"/api/v1/stages/{stage_id}",
        json={"name": "Muda De Fase", "step_id": _NEGOCIACAO_STEP_ID, "is_active": True},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["step_name"] == "Negociação"

    list_response = await client.get(
        "/api/v1/stages", params={"step_id": _NEGOCIACAO_STEP_ID}, headers=headers
    )
    by_id = {row["id"]: row["position"] for row in list_response.json()["items"]}
    assert by_id[stage_id] == max(by_id.values())


async def test_criar_etapa_com_nome_duplicado_na_mesma_fase_retorna_409(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    await _create_stage(client, headers, "Duplicada", _MARKETING_STEP_ID)

    response = await client.post(
        "/api/v1/stages",
        json={"name": "Duplicada", "step_id": _MARKETING_STEP_ID},
        headers=headers,
    )

    assert response.status_code == 409


async def test_atualizar_etapa_com_fase_inexistente_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    stage_id = await _create_stage(client, headers, "Etapa Válida")

    response = await client.put(
        f"/api/v1/stages/{stage_id}",
        json={"name": "Etapa Válida", "step_id": 999, "is_active": True},
        headers=headers,
    )

    assert response.status_code == 422


async def test_reordenacao_com_id_inexistente_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    stage_id = await _create_stage(client, headers, "Única")

    response = await client.post(
        "/api/v1/stages/reorder",
        json={"stage_ids": [stage_id, str(uuid.uuid4())]},
        headers=headers,
    )

    assert response.status_code == 422


async def test_transferencia_com_ids_validos_retorna_200(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origem = await _create_stage(client, headers, "Origem")
    destino = await _create_stage(client, headers, "Destino")

    response = await client.post(
        "/api/v1/stages/transfer",
        json={"from_id": origem, "to_id": destino},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["transferred_count"] == 0


async def test_estagnacao_com_dias_e_aceita(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)

    response = await client.post(
        "/api/v1/stages",
        json={
            "name": "Estagnação Configurada",
            "step_id": _MARKETING_STEP_ID,
            "enable_stagnant_days": True,
            "stagnant_days": 15,
        },
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["stagnant_days"] == 15


async def test_excluir_etapa_nao_bloqueia_ainda(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 4 existe no contrato (endpoint de transferência), mas nada referencia
    `stage_id` ainda — `lawsuits` só chega na spec 022 (Descobertas). Excluir hoje é
    incondicional."""
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    stage_id = await _create_stage(client, headers, "Etapa Solta")

    response = await client.delete(f"/api/v1/stages/{stage_id}", headers=headers)

    assert response.status_code == 204


async def test_reordenacao_persiste_e_e_transacional(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    primeira = await _create_stage(client, headers, "Primeira")
    segunda = await _create_stage(client, headers, "Segunda")
    terceira = await _create_stage(client, headers, "Terceira")

    response = await client.post(
        "/api/v1/stages/reorder",
        json={"stage_ids": [terceira, primeira, segunda]},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["reordered_count"] == 3

    list_response = await client.get(
        "/api/v1/stages", params={"step_id": _MARKETING_STEP_ID}, headers=headers
    )
    by_id = {row["id"]: row["position"] for row in list_response.json()["items"]}
    assert by_id[terceira] < by_id[primeira] < by_id[segunda]


async def test_reordenacao_com_fases_diferentes_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 5/8: reordenar mistura de fases diferentes não faz sentido — mesma classe de
    problema que "processo mudando de fase" (regra 8), testável hoje sem precisar da tabela
    de processos (spec 022)."""
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    marketing_stage = await _create_stage(client, headers, "Da Marketing", _MARKETING_STEP_ID)
    negociacao_stage = await _create_stage(client, headers, "Da Negociação", _NEGOCIACAO_STEP_ID)

    response = await client.post(
        "/api/v1/stages/reorder",
        json={"stage_ids": [marketing_stage, negociacao_stage]},
        headers=headers,
    )

    assert response.status_code == 422


async def test_transferencia_com_ids_iguais_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    stage_id = await _create_stage(client, headers, "Sozinha")

    response = await client.post(
        "/api/v1/stages/transfer",
        json={"from_id": stage_id, "to_id": stage_id},
        headers=headers,
    )

    assert response.status_code == 422


async def test_transferencia_com_etapa_inexistente_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    stage_id = await _create_stage(client, headers, "Existente")

    response = await client.post(
        "/api/v1/stages/transfer",
        json={"from_id": stage_id, "to_id": str(uuid.uuid4())},
        headers=headers,
    )

    assert response.status_code == 422


async def test_colaborador_recebe_403_ao_escrever(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador = await make_user(role=UserRole.COLABORADOR)
    headers = _auth_header(colaborador)

    list_response = await client.get("/api/v1/stages", headers=headers)
    assert list_response.status_code == 200

    create_response = await client.post(
        "/api/v1/stages",
        json={"name": "Não Autorizada", "step_id": _MARKETING_STEP_ID},
        headers=headers,
    )
    assert create_response.status_code == 403


async def test_tenant_a_nao_ve_etapa_de_tenant_b(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor_a = await make_user(role=UserRole.GESTOR)
    gestor_b = await make_user(role=UserRole.GESTOR)

    stage_id = await _create_stage(client, _auth_header(gestor_a), "Isolada")

    response = await client.get("/api/v1/stages", headers=_auth_header(gestor_b))

    ids = {item["id"] for item in response.json()["items"]}
    assert stage_id not in ids


async def test_put_etapa_inexistente_retorna_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)

    response = await client.put(
        f"/api/v1/stages/{uuid.uuid4()}",
        json={"name": "Não Existe", "step_id": _MARKETING_STEP_ID, "is_active": True},
        headers=_auth_header(gestor),
    )

    assert response.status_code == 404


async def test_delete_etapa_inexistente_retorna_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)

    response = await client.delete(f"/api/v1/stages/{uuid.uuid4()}", headers=_auth_header(gestor))

    assert response.status_code == 404


async def test_renomear_etapa_para_nome_existente_na_mesma_fase_retorna_409(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    await _create_stage(client, headers, "Etapa Um")
    etapa_dois = await _create_stage(client, headers, "Etapa Dois")

    response = await client.put(
        f"/api/v1/stages/{etapa_dois}",
        json={"name": "Etapa Um", "step_id": _MARKETING_STEP_ID, "is_active": True},
        headers=headers,
    )

    assert response.status_code == 409


async def test_mesmo_nome_em_fases_diferentes_e_permitido(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 6 (corrigida, spec 015 Descobertas): unicidade é por (tenant, fase) — a fonte
    real repete "PLANEJAMENTO" em duas fases distintas."""
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    await _create_stage(client, headers, "Repetido", _MARKETING_STEP_ID)

    response = await client.post(
        "/api/v1/stages",
        json={"name": "Repetido", "step_id": _NEGOCIACAO_STEP_ID},
        headers=headers,
    )

    assert response.status_code == 201


async def test_criar_etapa_com_fase_inexistente_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)

    response = await client.post(
        "/api/v1/stages",
        json={"name": "Órfã", "step_id": 999},
        headers=_auth_header(gestor),
    )

    assert response.status_code == 422


async def test_listagem_filtra_por_fase_status_e_busca(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    marketing_stage = await _create_stage(client, headers, "Só Marketing", _MARKETING_STEP_ID)
    negociacao_stage = await _create_stage(client, headers, "Só Negociação", _NEGOCIACAO_STEP_ID)

    step_filtered = await client.get(
        "/api/v1/stages", params={"step_id": _MARKETING_STEP_ID}, headers=headers
    )
    step_ids = {item["id"] for item in step_filtered.json()["items"]}
    assert marketing_stage in step_ids
    assert negociacao_stage not in step_ids

    await client.put(
        f"/api/v1/stages/{negociacao_stage}",
        json={"name": "Só Negociação", "step_id": _NEGOCIACAO_STEP_ID, "is_active": False},
        headers=headers,
    )
    status_filtered = await client.get(
        "/api/v1/stages", params={"status": "inactive"}, headers=headers
    )
    status_ids = {item["id"] for item in status_filtered.json()["items"]}
    assert negociacao_stage in status_ids
    assert marketing_stage not in status_ids

    query_filtered = await client.get("/api/v1/stages", params={"q": "Marketing"}, headers=headers)
    query_names = {item["name"] for item in query_filtered.json()["items"]}
    assert query_names == {"Só Marketing"}
