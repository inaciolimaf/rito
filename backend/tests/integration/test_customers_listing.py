import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.tokens import create_access_token
from app.domain.users.models import UserRole
from tests.clock import hoje
from tests.integration.conftest import SeededUser


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


async def _create_origin(client: AsyncClient, headers: dict[str, str], name: str) -> str:
    response = await client.post("/api/v1/customer-origins", json={"name": name}, headers=headers)
    assert response.status_code == 201
    result: str = response.json()["id"]
    return result


async def _create_customer(
    client: AsyncClient, headers: dict[str, str], origin_id: str, **overrides: object
) -> str:
    payload: dict[str, object] = {"type": "PF", "name": "Cliente", "origin_id": origin_id}
    payload.update(overrides)
    response = await client.post("/api/v1/customers", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    result: str = response.json()["id"]
    return result


async def test_busca_parcial_ignora_acento(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")
    await _create_customer(client, headers, origin_id, name="José da Silva")
    await _create_customer(client, headers, origin_id, name="Outra Pessoa")

    response = await client.get("/api/v1/customers", params={"q": "jose"}, headers=headers)

    assert response.status_code == 200
    names = {item["name"] for item in response.json()["items"]}
    assert names == {"José da Silva"}


async def test_filtros_combinam_com_and(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_a = await _create_origin(client, headers, "Origem A")
    origin_b = await _create_origin(client, headers, "Origem B")
    await _create_customer(
        client, headers, origin_a, name="Combina Tudo", state="SP", city="São Paulo"
    )
    await _create_customer(
        client, headers, origin_a, name="Errou Cidade", state="SP", city="Campinas"
    )
    await _create_customer(
        client, headers, origin_b, name="Errou Origem", state="SP", city="São Paulo"
    )

    response = await client.get(
        "/api/v1/customers",
        params={"state": "SP", "city": "São Paulo", "origin_id": origin_a},
        headers=headers,
    )

    assert response.status_code == 200
    names = {item["name"] for item in response.json()["items"]}
    assert names == {"Combina Tudo"}


async def test_paginacao_keyset_e_estavel_com_insercao_concorrente(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")
    await _create_customer(client, headers, origin_id, name="Ana")
    await _create_customer(client, headers, origin_id, name="Bruno")
    await _create_customer(client, headers, origin_id, name="Carla")

    page1 = await client.get(
        "/api/v1/customers", params={"sort": "name", "order": "asc", "limit": 2}, headers=headers
    )
    assert page1.status_code == 200
    page1_names = [item["name"] for item in page1.json()["items"]]
    assert page1_names == ["Ana", "Bruno"]
    cursor = page1.json()["next_cursor"]
    assert cursor is not None

    # Inserção concorrente de um registro que ordenaria ANTES do cursor não deve
    # duplicar nem pular itens da página seguinte.
    await _create_customer(client, headers, origin_id, name="Abelardo")

    page2 = await client.get(
        "/api/v1/customers",
        params={"sort": "name", "order": "asc", "limit": 2, "cursor": cursor},
        headers=headers,
    )
    assert page2.status_code == 200
    page2_names = [item["name"] for item in page2.json()["items"]]
    assert page2_names == ["Carla"]


async def test_stats_com_seed_deterministico(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_a = await _create_origin(client, headers, "Indicação Stats")
    origin_b = await _create_origin(client, headers, "Facebook Stats")
    await _create_customer(client, headers, origin_a, name="C1", occupation="Advogado")
    await _create_customer(client, headers, origin_a, name="C2", occupation="Advogado")
    await _create_customer(client, headers, origin_b, name="C3", occupation="Médico")

    response = await client.get("/api/v1/customers/stats", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["with_active_lawsuit"] == 0
    assert body["without_active_lawsuit"] == 3
    origins_by_name = {item["name"]: item["count"] for item in body["top_origins"]}
    assert origins_by_name["Indicação Stats"] == 2
    assert origins_by_name["Facebook Stats"] == 1
    occupations_by_name = {item["name"]: item["count"] for item in body["top_occupations"]}
    assert occupations_by_name["Advogado"] == 2
    assert occupations_by_name["Médico"] == 1


async def test_faixas_etarias_incluindo_nao_informado(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")
    today = hoje()

    def _years_ago(years: int) -> str:
        return (today.replace(year=today.year - years)).isoformat()

    await _create_customer(client, headers, origin_id, name="Crianca", birthdate=_years_ago(10))
    await _create_customer(client, headers, origin_id, name="Adulto", birthdate=_years_ago(30))
    await _create_customer(client, headers, origin_id, name="Idoso", birthdate=_years_ago(70))
    await _create_customer(client, headers, origin_id, name="SemData")

    response = await client.get("/api/v1/customers/stats", headers=headers)

    assert response.status_code == 200
    ranges_by_label = {item["name"]: item["count"] for item in response.json()["age_ranges"]}
    assert ranges_by_label["0-17"] == 1
    assert ranges_by_label["25-34"] == 1
    assert ranges_by_label["65+"] == 1
    assert ranges_by_label["Não informado"] == 1


async def test_aniversariantes_do_dia_e_do_mes(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")
    today = hoje()
    other_day_this_month = today.replace(day=1) if today.day != 1 else today.replace(day=2)

    await _create_customer(
        client,
        headers,
        origin_id,
        name="Aniversariante Hoje",
        birthdate=today.replace(year=today.year - 40).isoformat(),
    )
    await _create_customer(
        client,
        headers,
        origin_id,
        name="Aniversariante Do Mes",
        birthdate=other_day_this_month.replace(year=today.year - 25).isoformat(),
    )

    day_response = await client.get(
        "/api/v1/customers/birthdays", params={"scope": "day"}, headers=headers
    )
    assert day_response.status_code == 200
    day_names = {item["name"] for item in day_response.json()}
    assert "Aniversariante Hoje" in day_names
    assert "Aniversariante Do Mes" not in day_names

    month_response = await client.get(
        "/api/v1/customers/birthdays", params={"scope": "month"}, headers=headers
    )
    assert month_response.status_code == 200
    month_names = {item["name"] for item in month_response.json()}
    assert "Aniversariante Hoje" in month_names
    assert "Aniversariante Do Mes" in month_names


async def test_export_respeita_filtros(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")
    await _create_customer(client, headers, origin_id, name="Exportar Este", state="RJ")
    await _create_customer(client, headers, origin_id, name="Nao Exportar", state="SP")

    response = await client.post(
        "/api/v1/customers/export",
        json={"format": "xlsx", "filters": {"state": "RJ"}},
        headers=headers,
    )

    assert response.status_code == 200
    assert (
        response.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert len(response.content) > 0

    pdf_response = await client.post(
        "/api/v1/customers/export",
        json={"format": "pdf", "filters": {"state": "RJ"}},
        headers=headers,
    )
    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"] == "application/pdf"
    assert len(pdf_response.content) > 0


async def test_arquivados_ocultos_por_padrao(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    admin = await make_user(role=UserRole.ADMINISTRADOR, tenant_id=gestor.tenant_id)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")
    archived_id = await _create_customer(client, headers, origin_id, name="Arquivado")
    active_id = await _create_customer(client, headers, origin_id, name="Ativo")
    await client.delete(f"/api/v1/customers/{archived_id}", headers=_auth_header(admin))

    default_response = await client.get("/api/v1/customers", headers=headers)
    default_ids = {item["id"] for item in default_response.json()["items"]}
    assert active_id in default_ids
    assert archived_id not in default_ids

    archived_response = await client.get(
        "/api/v1/customers", params={"archived": "true"}, headers=headers
    )
    archived_ids = {item["id"] for item in archived_response.json()["items"]}
    assert archived_id in archived_ids
    assert active_id not in archived_ids


async def test_whatsapp_link_bem_formado(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")
    await _create_customer(client, headers, origin_id, name="Com Celular", cellphone="11999998888")
    await _create_customer(client, headers, origin_id, name="Sem Celular")

    response = await client.get("/api/v1/customers", headers=headers)

    items_by_name = {item["name"]: item for item in response.json()["items"]}
    assert items_by_name["Com Celular"]["whatsapp_link"] == "https://wa.me/5511999998888"
    assert items_by_name["Sem Celular"]["whatsapp_link"] is None


async def test_type_filtra_por_pessoa_fisica_ou_juridica(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")
    await _create_customer(client, headers, origin_id, type="PF", name="Pessoa Fisica")
    await _create_customer(
        client,
        headers,
        origin_id,
        type="PJ",
        name="Pessoa Juridica",
        identification="11222333000181",
    )

    response = await client.get("/api/v1/customers", params={"type": "PJ"}, headers=headers)

    names = {item["name"] for item in response.json()["items"]}
    assert names == {"Pessoa Juridica"}


async def test_has_active_lawsuit_nao_encontra_nada_ainda(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra fora de alcance (Descobertas): lawsuits só chega na spec 022 — nenhum contato
    tem processo ativo hoje."""
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")
    await _create_customer(client, headers, origin_id, name="Qualquer Um")

    response = await client.get(
        "/api/v1/customers", params={"has_active_lawsuit": "true"}, headers=headers
    )

    assert response.json()["items"] == []


async def test_customer_inexistente_no_check_duplicate_nao_conflita_com_stats(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Sanity check de ordenação de rotas: /customers/stats, /customers/birthdays e
    /customers/check-duplicate não podem ser interpretadas como /customers/{customer_id}."""
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)

    stats = await client.get("/api/v1/customers/stats", headers=headers)
    birthdays = await client.get(
        "/api/v1/customers/birthdays", params={"scope": "day"}, headers=headers
    )

    assert stats.status_code == 200
    assert birthdays.status_code == 200


async def test_ordenacao_por_created_at_desc_por_padrao(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")
    first_id = await _create_customer(client, headers, origin_id, name="Primeiro")
    second_id = await _create_customer(client, headers, origin_id, name="Segundo")

    response = await client.get("/api/v1/customers", headers=headers)

    ids = [item["id"] for item in response.json()["items"]]
    assert ids.index(second_id) < ids.index(first_id)


async def test_created_from_e_created_to_filtram_periodo(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")
    await _create_customer(client, headers, origin_id, name="Criado Agora")

    tomorrow = (hoje() + timedelta(days=1)).isoformat()
    yesterday = (hoje() - timedelta(days=1)).isoformat()

    in_range = await client.get(
        "/api/v1/customers",
        params={"created_from": yesterday, "created_to": tomorrow},
        headers=headers,
    )
    out_of_range = await client.get(
        "/api/v1/customers",
        params={"created_from": tomorrow, "created_to": tomorrow},
        headers=headers,
    )

    assert len(in_range.json()["items"]) == 1
    assert len(out_of_range.json()["items"]) == 0


async def test_identification_exata_no_q(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")
    await _create_customer(client, headers, origin_id, name="Com CPF", identification="11144477735")
    await _create_customer(client, headers, origin_id, name="Outro Com CPF Parecido")

    response = await client.get(
        "/api/v1/customers", params={"q": "111.444.777-35"}, headers=headers
    )

    names = {item["name"] for item in response.json()["items"]}
    assert names == {"Com CPF"}


async def test_aniversariantes_no_filtro_da_listagem(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Cobre `birthdays=day|month` como filtro de `GET /customers` (diferente do endpoint
    dedicado `/customers/birthdays`, exercitado em outro teste)."""
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")
    today = hoje()
    await _create_customer(
        client,
        headers,
        origin_id,
        name="Faz Aniversario Hoje",
        birthdate=today.replace(year=today.year - 20).isoformat(),
    )
    await _create_customer(client, headers, origin_id, name="Sem Aniversario Hoje")

    day_response = await client.get(
        "/api/v1/customers", params={"birthdays": "day"}, headers=headers
    )
    month_response = await client.get(
        "/api/v1/customers", params={"birthdays": "month"}, headers=headers
    )

    assert {item["name"] for item in day_response.json()["items"]} == {"Faz Aniversario Hoje"}
    assert {item["name"] for item in month_response.json()["items"]} == {"Faz Aniversario Hoje"}


async def test_variacao_vs_mes_anterior_com_cadastro_no_mes_passado(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    admin_engine: AsyncEngine,
) -> None:
    """Cobre o ramo `last_month_count > 0` do cálculo de variação — `created_at` é
    `server_default`, não dá para setar via API, então volta no tempo direto no banco
    (admin_engine bypassa RLS, só para setup de teste)."""
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")
    last_month_id = await _create_customer(client, headers, origin_id, name="Mês Passado")
    await _create_customer(client, headers, origin_id, name="Este Mês")

    this_month_start = hoje().replace(day=1)
    last_month_end = this_month_start - timedelta(days=1)
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("UPDATE customers SET created_at = :created_at WHERE id = :id"),
            {"created_at": last_month_end, "id": last_month_id},
        )

    response = await client.get("/api/v1/customers/stats", headers=headers)

    assert response.status_code == 200
    assert isinstance(response.json()["variation_vs_last_month"], float)


async def test_top_ocupacoes_agrupa_o_resto_em_outros(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 5: top 10 + "Outros" — 11 ocupações distintas, uma só cada, para forçar a
    11ª a cair no agrupamento."""
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")
    for index in range(11):
        await _create_customer(
            client, headers, origin_id, name=f"Cliente {index}", occupation=f"Ocupacao {index}"
        )

    response = await client.get("/api/v1/customers/stats", headers=headers)

    names = {item["name"] for item in response.json()["top_occupations"]}
    assert "Outros" in names
    assert len(response.json()["top_occupations"]) == 11


async def test_get_customer_id_aleatorio_nao_confunde_com_stats(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)

    response = await client.get(f"/api/v1/customers/{uuid.uuid4()}", headers=_auth_header(gestor))

    assert response.status_code == 404


async def _create_lawsuit_for(
    client: AsyncClient,
    headers: dict[str, str],
    seeded: SeededUser,
    customer_id: str,
    *,
    archived: bool = False,
) -> str:
    """Processo com o contato como parte (spec 023). `archived=True` cobre o complemento
    da regra 5: processo arquivado não conta como ativo."""
    suffix = uuid.uuid4().hex[:8]
    group = await client.post(
        "/api/v1/action-groups", json={"name": f"Grupo {suffix}"}, headers=headers
    )
    assert group.status_code == 201
    lawsuit_type = await client.post(
        "/api/v1/lawsuit-types",
        json={"name": f"Tipo {suffix}", "action_group_id": group.json()["id"]},
        headers=headers,
    )
    assert lawsuit_type.status_code == 201
    stage = await client.post(
        "/api/v1/stages", json={"name": f"Etapa {suffix}", "step_id": 1}, headers=headers
    )
    assert stage.status_code == 201

    response = await client.post(
        "/api/v1/lawsuits",
        json={
            "user_id": str(seeded.user_id),
            "lawsuit_type_id": lawsuit_type.json()["id"],
            "stage_id": stage.json()["id"],
            "parties": [{"customer_id": customer_id, "pole": "ATIVO", "is_client": True}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    lawsuit_id: str = response.json()["id"]

    if archived:
        # Não há rota /archive: o DELETE do processo é soft delete e é ele quem liga
        # `is_archived` (spec 028, regra 7 — router.py:681).
        archive = await client.delete(f"/api/v1/lawsuits/{lawsuit_id}", headers=headers)
        assert archive.status_code == 204, archive.text
    return lawsuit_id


async def test_filtro_de_processo_ativo_e_seu_complemento(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Spec 101, regra 5. Antes desta spec `has_active_lawsuit=true` casava com
    `Customer.id == uuid4()` — ou seja, nunca achava nada."""
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, f"Origem {uuid.uuid4().hex[:8]}")
    com_ativo = await _create_customer(client, headers, origin_id, name="Com Processo Ativo")
    so_arquivado = await _create_customer(client, headers, origin_id, name="So Arquivado")
    sem_processo = await _create_customer(client, headers, origin_id, name="Sem Processo")
    await _create_lawsuit_for(client, headers, gestor, com_ativo)
    await _create_lawsuit_for(client, headers, gestor, so_arquivado, archived=True)

    com = await client.get(
        "/api/v1/customers", params={"has_active_lawsuit": True}, headers=headers
    )
    ids_com = [item["id"] for item in com.json()["items"]]
    assert ids_com == [com_ativo]

    sem = await client.get(
        "/api/v1/customers", params={"has_active_lawsuit": False}, headers=headers
    )
    ids_sem = [item["id"] for item in sem.json()["items"]]
    assert set(ids_sem) == {so_arquivado, sem_processo}

    # Omitido não filtra — os três aparecem.
    todos = await client.get("/api/v1/customers", headers=headers)
    assert {item["id"] for item in todos.json()["items"]} == {
        com_ativo,
        so_arquivado,
        sem_processo,
    }


async def test_contato_com_dois_processos_ativos_aparece_uma_vez(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Spec 101, regra 5: a condição é EXISTS, não JOIN — dois processos ativos não
    duplicam a linha nem inflam `total`."""
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, f"Origem {uuid.uuid4().hex[:8]}")
    customer_id = await _create_customer(client, headers, origin_id, name="Dois Processos")
    await _create_lawsuit_for(client, headers, gestor, customer_id)
    await _create_lawsuit_for(client, headers, gestor, customer_id)

    response = await client.get(
        "/api/v1/customers", params={"has_active_lawsuit": True}, headers=headers
    )

    assert [item["id"] for item in response.json()["items"]] == [customer_id]
    assert response.json()["total"] == 1


async def test_contadores_de_processo_ativo_somam_o_total(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Spec 101, regra 6: os contadores do dashboard deixam de ser a constante 0/total e
    batem com a contagem do filtro da regra 5 sobre a mesma base."""
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, f"Origem {uuid.uuid4().hex[:8]}")
    com_ativo = await _create_customer(client, headers, origin_id, name="Com Ativo")
    await _create_customer(client, headers, origin_id, name="Sem Ativo")
    await _create_lawsuit_for(client, headers, gestor, com_ativo)

    stats = (await client.get("/api/v1/customers/stats", headers=headers)).json()

    assert stats["with_active_lawsuit"] == 1
    assert stats["without_active_lawsuit"] == 1
    assert stats["with_active_lawsuit"] + stats["without_active_lawsuit"] == stats["total"]

    filtrados = await client.get(
        "/api/v1/customers", params={"has_active_lawsuit": True}, headers=headers
    )
    assert filtrados.json()["total"] == stats["with_active_lawsuit"]
