import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.clock import Clock
from app.domain.users.models import UserRole
from app.main import app
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import _auth_header
from tests.integration.test_lawsuits_listing import LawsuitFactory, _make_factory
from tests.perf import query_budget


@pytest.fixture
async def factory(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> LawsuitFactory:
    return await _make_factory(client, make_user, app_session_factory)


async def _create_task_type(client: AsyncClient, headers: dict[str, str], reward: int = 8) -> str:
    response = await client.post(
        "/api/v1/task-types",
        json={
            "name": f"Tarefa {uuid.uuid4().hex[:8]}",
            "complexity": "SIMPLES",
            "duration": "MIN_15",
            "reward": reward,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return str(response.json()["id"])


async def _create_post(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    lawsuit_id: str,
    task_type_id: str,
    user_ids: list[str] | None = None,
    **extra: object,
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/posts",
        json={
            "lawsuit_id": lawsuit_id,
            "task_type_id": task_type_id,
            "user_ids": user_ids or [],
            "scheduled_date": "2026-08-10",
            **extra,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.json()
    return dict(response.json())


async def test_crud_com_multiplos_responsaveis(
    client: AsyncClient, factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    headers = factory.headers
    segundo = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, headers)

    created = await _create_post(
        client,
        headers,
        lawsuit_id=lawsuit_id,
        task_type_id=task_type_id,
        user_ids=[str(factory.gestor.user_id), str(segundo.user_id)],
        scheduled_time="14:30:00",
        deadline_date="2026-08-05",  # regra 7: prazo fatal pode ser anterior
        location="Fórum Central",
        comments="Levar documentos",
    )
    assert len(created["assignees"]) == 2
    assert created["reward_snapshot"] == 8

    post_id = str(created["id"])
    fetched = await client.get(f"/api/v1/posts/{post_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["location"] == "Fórum Central"

    listed = await client.get(f"/api/v1/lawsuits/{lawsuit_id}/posts", headers=headers)
    assert [item["id"] for item in listed.json()] == [post_id]

    updated = await client.put(
        f"/api/v1/posts/{post_id}",
        json={
            "lawsuit_id": lawsuit_id,
            "task_type_id": task_type_id,
            "user_ids": [str(segundo.user_id)],
            "scheduled_date": "2026-08-12",
            "end_date": "2026-08-12",
            "end_time": "18:00:00",
        },
        headers=headers,
    )
    assert updated.status_code == 200
    assert [a["id"] for a in updated.json()["assignees"]] == [str(segundo.user_id)]

    deleted = await client.delete(f"/api/v1/posts/{post_id}", headers=headers)
    assert deleted.status_code == 204
    assert (await client.get(f"/api/v1/posts/{post_id}", headers=headers)).status_code == 404


async def test_atribuicao_por_time_expande_somente_membros_ativos(
    client: AsyncClient, factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    headers = factory.headers
    ativo = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    inativo = await make_user(
        tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR, is_active=False
    )
    squad = await client.post(
        "/api/v1/squads",
        json={
            "name": f"Time {uuid.uuid4().hex[:6]}",
            "member_ids": [str(ativo.user_id), str(inativo.user_id)],
        },
        headers=headers,
    )
    assert squad.status_code == 201

    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, headers)
    created = await _create_post(
        client,
        headers,
        lawsuit_id=lawsuit_id,
        task_type_id=task_type_id,
        squad_id=str(squad.json()["id"]),
    )
    # Regra 2: expande os ativos no momento da criação — o inativo fica de fora.
    assert [a["id"] for a in created["assignees"]] == [str(ativo.user_id)]


async def test_sem_responsavel_retorna_422(client: AsyncClient, factory: LawsuitFactory) -> None:
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, factory.headers)
    response = await client.post(
        "/api/v1/posts",
        json={"lawsuit_id": lawsuit_id, "task_type_id": task_type_id, "user_ids": []},
        headers=factory.headers,
    )
    assert response.status_code == 422


async def test_duplicata_retorna_409_com_id_existente(
    client: AsyncClient, factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, factory.headers)
    primeiro = await _create_post(
        client,
        factory.headers,
        lawsuit_id=lawsuit_id,
        task_type_id=task_type_id,
        user_ids=[str(factory.gestor.user_id)],
    )

    duplicado = await client.post(
        "/api/v1/posts",
        json={
            "lawsuit_id": lawsuit_id,
            "task_type_id": task_type_id,
            "user_ids": [str(factory.gestor.user_id)],
            "scheduled_date": "2026-08-10",
        },
        headers=factory.headers,
    )
    assert duplicado.status_code == 409
    # Regra 4: o 409 carrega o id da tarefa existente (membro de extensão RFC 7807).
    assert duplicado.json()["existing_id"] == primeiro["id"]

    # Conjunto de responsáveis diferente NÃO é duplicata (regra 4).
    outro = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    nao_duplicado = await client.post(
        "/api/v1/posts",
        json={
            "lawsuit_id": lawsuit_id,
            "task_type_id": task_type_id,
            "user_ids": [str(factory.gestor.user_id), str(outro.user_id)],
            "scheduled_date": "2026-08-10",
        },
        headers=factory.headers,
    )
    assert nao_duplicado.status_code == 201


async def test_end_time_sem_end_date_retorna_422(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, factory.headers)
    response = await client.post(
        "/api/v1/posts",
        json={
            "lawsuit_id": lawsuit_id,
            "task_type_id": task_type_id,
            "user_ids": [str(factory.gestor.user_id)],
            "scheduled_date": "2026-08-10",
            "end_time": "18:00:00",
        },
        headers=factory.headers,
    )
    assert response.status_code == 422


async def test_end_date_anterior_retorna_422(client: AsyncClient, factory: LawsuitFactory) -> None:
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, factory.headers)
    response = await client.post(
        "/api/v1/posts",
        json={
            "lawsuit_id": lawsuit_id,
            "task_type_id": task_type_id,
            "user_ids": [str(factory.gestor.user_id)],
            "scheduled_date": "2026-08-10",
            "end_date": "2026-08-09",
        },
        headers=factory.headers,
    )
    assert response.status_code == 422


async def test_reward_snapshot_congela_na_criacao(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    headers = factory.headers
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, headers, reward=8)
    created = await _create_post(
        client,
        headers,
        lawsuit_id=lawsuit_id,
        task_type_id=task_type_id,
        user_ids=[str(factory.gestor.user_id)],
    )

    # Regra 3: mudar o catálogo depois não reescreve o histórico.
    detalhe = await client.get("/api/v1/task-types", headers=headers)
    tipo = next(item for item in detalhe.json()["items"] if item["id"] == task_type_id)
    await client.put(
        f"/api/v1/task-types/{task_type_id}",
        json={"name": tipo["name"], "reward": 99, "is_active": True},
        headers=headers,
    )

    fetched = await client.get(f"/api/v1/posts/{created['id']}", headers=headers)
    assert fetched.json()["reward_snapshot"] == 8


async def test_excluir_processo_remove_tarefas_no_hard_delete(
    client: AsyncClient, factory: LawsuitFactory, admin_engine: AsyncEngine
) -> None:
    """Regra 8: a FK com ON DELETE CASCADE remove as tarefas junto com o processo —
    testado no hard delete direto no banco (o delete da API é soft desde a 022)."""
    headers = factory.headers
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, headers)
    created = await _create_post(
        client,
        headers,
        lawsuit_id=lawsuit_id,
        task_type_id=task_type_id,
        user_ids=[str(factory.gestor.user_id)],
    )

    # admin_engine é o superusuário (bypassa RLS) — o delete é do banco, sem API.
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM lawsuits WHERE id = CAST(:id AS uuid)"), {"id": lawsuit_id}
        )
        remaining = await conn.execute(
            text("SELECT count(*) FROM posts WHERE id = CAST(:id AS uuid)"),
            {"id": str(created["id"])},
        )
        assert remaining.scalar_one() == 0


async def test_posts_isolados_entre_tenants(
    client: AsyncClient, factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, factory.headers)
    created = await _create_post(
        client,
        factory.headers,
        lawsuit_id=lawsuit_id,
        task_type_id=task_type_id,
        user_ids=[str(factory.gestor.user_id)],
    )

    outro_gestor = await make_user(role=UserRole.GESTOR)
    headers_b = _auth_header(outro_gestor)
    resposta_b = await client.get(f"/api/v1/posts/{created['id']}", headers=headers_b)
    assert resposta_b.status_code == 404
    assert (
        await client.get(f"/api/v1/lawsuits/{lawsuit_id}/posts", headers=headers_b)
    ).json() == []


async def test_tipo_em_uso_exige_transferencia(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 5 da spec 031, plugada agora que `posts` existe: excluir tipo em uso →
    409; transferindo antes, a exclusão libera."""
    headers = factory.headers
    lawsuit_id = await factory.create()
    tipo_em_uso = await _create_task_type(client, headers)
    tipo_destino = await _create_task_type(client, headers)
    await _create_post(
        client,
        headers,
        lawsuit_id=lawsuit_id,
        task_type_id=tipo_em_uso,
        user_ids=[str(factory.gestor.user_id)],
    )

    bloqueado = await client.delete(f"/api/v1/task-types/{tipo_em_uso}", headers=headers)
    assert bloqueado.status_code == 409

    transferido = await client.post(
        "/api/v1/task-types/transfer",
        json={"from_id": tipo_em_uso, "to_id": tipo_destino},
        headers=headers,
    )
    assert transferido.json() == {"transferred_count": 1}

    liberado = await client.delete(f"/api/v1/task-types/{tipo_em_uso}", headers=headers)
    assert liberado.status_code == 204


# ---------------------------------------------------------------------------------------
# Tela de Atividades (spec 128) — a listagem global de tarefas.
#
# `date.today()` e não data fixa: a regra das futuras (033, regra 7) e o status ATRASADA
# comparam com o dia do escritório, e um literal no calendário só passaria enquanto a
# semana não virasse. As distâncias são de 2 dias ou mais para o fuso do escritório
# (America/Sao_Paulo) nunca empurrar um caso para o outro lado da meia-noite.
# ---------------------------------------------------------------------------------------

# `Clock()` e não `date.today()`: é o relógio do escritório (spec 114) — o mesmo que o
# endpoint usa —, e o do processo roda em UTC.
HOJE = Clock().today()
ONTEM = HOJE - timedelta(days=2)
AMANHA = HOJE + timedelta(days=2)
DEPOIS = HOJE + timedelta(days=5)


async def _list_activities(
    client: AsyncClient, headers: dict[str, str], **params: object
) -> dict[str, Any]:
    query = {chave: str(valor) for chave, valor in params.items() if valor is not None}
    response = await client.get("/api/v1/posts", params=query, headers=headers)
    assert response.status_code == 200, response.text
    return dict(response.json())


def _ids(page: dict[str, Any]) -> list[str]:
    return [item["id"] for item in page["items"]]


async def test_atividades_contrato_e_colunas(client: AsyncClient, factory: LawsuitFactory) -> None:
    """Regra 1: `{items, next_cursor, total}`. A linha traz o que a tela mostra —
    tarefa, processo, responsáveis, datas, prioridade e status derivado."""
    headers = factory.headers
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, headers)
    criada = await _create_post(
        client,
        headers,
        lawsuit_id=lawsuit_id,
        task_type_id=task_type_id,
        user_ids=[str(factory.gestor.user_id)],
        scheduled_date=AMANHA.isoformat(),
        deadline_date=DEPOIS.isoformat(),
        is_urgent=True,
    )

    page = await _list_activities(client, headers)
    assert page["total"] == 1
    assert page["next_cursor"] is None
    linha = page["items"][0]
    assert linha["id"] == criada["id"]
    assert linha["lawsuit_id"] == lawsuit_id
    assert linha["task_type_name"] == criada["task_type_name"]
    assert linha["assignee_names"] == ["Usuário de Teste"]
    assert linha["assignees_total"] == 1
    assert linha["scheduled_date"] == AMANHA.isoformat()
    assert linha["deadline_date"] == DEPOIS.isoformat()
    assert linha["is_urgent"] is True
    assert linha["status"] == "PENDENTE"


async def test_atividades_keyset_nao_repete_nem_pula(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regras 1 e 6: duas páginas cobrem o conjunto exatamente uma vez, e a tarefa SEM
    data do compromisso sai por último em vez de sumir — que é o que aconteceria se o
    cursor comparasse `(NULL, id)`."""
    headers = factory.headers
    lawsuit_id = await factory.create()
    datas = [AMANHA, DEPOIS, None]
    esperados: list[str] = []
    for data in datas:
        task_type_id = await _create_task_type(client, headers)
        criada = await _create_post(
            client,
            headers,
            lawsuit_id=lawsuit_id,
            task_type_id=task_type_id,
            user_ids=[str(factory.gestor.user_id)],
            scheduled_date=data.isoformat() if data else None,
        )
        esperados.append(str(criada["id"]))

    primeira = await _list_activities(client, headers, limit=2)
    assert primeira["total"] == 3
    assert primeira["next_cursor"] is not None
    segunda = await _list_activities(client, headers, limit=2, cursor=primeira["next_cursor"])

    vistos = _ids(primeira) + _ids(segunda)
    assert len(vistos) == 3
    assert set(vistos) == set(esperados)
    # Sem data ordena no fim (regra 6), não no começo nem fora da lista.
    assert vistos[-1] == esperados[2]


async def test_atividades_visoes_pendente_concluida_atrasada(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 5: `pending` é o default; concluir tira da visão de pendentes e põe na de
    concluídas; `overdue` é pendente com a data limite no passado."""
    headers = factory.headers
    lawsuit_id = await factory.create()
    futura_id = await _create_task_type(client, headers)
    atrasada_id = await _create_task_type(client, headers)
    pendente = await _create_post(
        client,
        headers,
        lawsuit_id=lawsuit_id,
        task_type_id=futura_id,
        user_ids=[str(factory.gestor.user_id)],
        scheduled_date=AMANHA.isoformat(),
    )
    atrasada = await _create_post(
        client,
        headers,
        lawsuit_id=lawsuit_id,
        task_type_id=atrasada_id,
        user_ids=[str(factory.gestor.user_id)],
        scheduled_date=ONTEM.isoformat(),
    )

    assert set(_ids(await _list_activities(client, headers))) == {
        pendente["id"],
        atrasada["id"],
    }
    vencidas = await _list_activities(client, headers, view="overdue")
    assert _ids(vencidas) == [atrasada["id"]]
    assert vencidas["items"][0]["status"] == "ATRASADA"

    concluida = await client.post(
        f"/api/v1/posts/{atrasada['id']}/complete", json={}, headers=headers
    )
    assert concluida.status_code == 200
    assert _ids(await _list_activities(client, headers)) == [pendente["id"]]
    fechadas = await _list_activities(client, headers, view="completed")
    assert _ids(fechadas) == [atrasada["id"]]
    assert fechadas["items"][0]["status"] == "CONCLUIDA"
    assert len(_ids(await _list_activities(client, headers, view="all"))) == 2


async def test_atividades_periodo_incide_sobre_o_eixo_escolhido(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 4: o mesmo par de datas filtra compromisso, prazo fatal ou conclusão
    conforme `column` — e o intervalo é aberto dos dois lados."""
    headers = factory.headers
    lawsuit_id = await factory.create()
    perto_id = await _create_task_type(client, headers)
    longe_id = await _create_task_type(client, headers)
    perto = await _create_post(
        client,
        headers,
        lawsuit_id=lawsuit_id,
        task_type_id=perto_id,
        user_ids=[str(factory.gestor.user_id)],
        scheduled_date=AMANHA.isoformat(),
        deadline_date=DEPOIS.isoformat(),
    )
    longe = await _create_post(
        client,
        headers,
        lawsuit_id=lawsuit_id,
        task_type_id=longe_id,
        user_ids=[str(factory.gestor.user_id)],
        scheduled_date=DEPOIS.isoformat(),
    )

    por_compromisso = await _list_activities(
        client, headers, column="scheduled", date_to=AMANHA.isoformat()
    )
    assert _ids(por_compromisso) == [perto["id"]]

    # Mesmo intervalo, outro eixo: pelo prazo fatal só a que TEM prazo entra.
    por_prazo = await _list_activities(
        client, headers, column="deadline", date_from=DEPOIS.isoformat()
    )
    assert _ids(por_prazo) == [perto["id"]]

    await client.post(f"/api/v1/posts/{longe['id']}/complete", json={}, headers=headers)
    por_conclusao = await _list_activities(
        client, headers, view="completed", column="completed", date_from=HOJE.isoformat()
    )
    assert _ids(por_conclusao) == [longe["id"]]


async def test_atividades_filtros_de_pessoa_prioridade_e_tipo(
    client: AsyncClient, factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Filtros do §6: responsável, remetente (que eu recebi / que eu enviei), prioridade
    (OR entre as flags) e tipo de tarefa."""
    headers = factory.headers
    colega = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    lawsuit_id = await factory.create()
    minha_id = await _create_task_type(client, headers)
    dele_id = await _create_task_type(client, headers)
    minha = await _create_post(
        client,
        headers,
        lawsuit_id=lawsuit_id,
        task_type_id=minha_id,
        user_ids=[str(factory.gestor.user_id)],
        scheduled_date=AMANHA.isoformat(),
        is_important=True,
    )
    dele = await _create_post(
        client,
        headers,
        lawsuit_id=lawsuit_id,
        task_type_id=dele_id,
        user_ids=[str(colega.user_id)],
        scheduled_date=AMANHA.isoformat(),
    )

    recebidas = await _list_activities(client, headers, sender="received")
    assert _ids(recebidas) == [minha["id"]]
    # Enviei as duas: o gestor criou ambas.
    assert len(_ids(await _list_activities(client, headers, sender="sent"))) == 2
    assert _ids(await _list_activities(client, headers, assignee_id=str(colega.user_id))) == [
        dele["id"]
    ]
    assert _ids(await _list_activities(client, headers, priority="important,urgent")) == [
        minha["id"]
    ]
    assert _ids(await _list_activities(client, headers, task_type_id=dele_id)) == [dele["id"]]


async def test_atividade_futura_oculta_ate_a_data(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 3 (033, regra 7): futura só aparece na data — ou quando pedida."""
    headers = factory.headers
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, headers)
    futura = await _create_post(
        client,
        headers,
        lawsuit_id=lawsuit_id,
        task_type_id=task_type_id,
        user_ids=[str(factory.gestor.user_id)],
        scheduled_date=DEPOIS.isoformat(),
        is_future=True,
    )

    assert (await _list_activities(client, headers))["total"] == 0
    com_futuras = await _list_activities(client, headers, include_future="true")
    assert _ids(com_futuras) == [futura["id"]]


async def test_atividade_privada_de_terceiro_nao_aparece_nem_para_gestor(
    client: AsyncClient, factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 2 (033, regra 8): a tarefa privada de outro não entra na listagem — e não
    entra nem redigida, nem no `total`, nem no export. Nem para o GESTOR."""
    headers = factory.headers
    colaborador = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    headers_colaborador = _auth_header(colaborador)
    lawsuit_id = await factory.create()
    privada_id = await _create_task_type(client, headers)
    publica_id = await _create_task_type(client, headers)

    privada = await _create_post(
        client,
        headers_colaborador,
        lawsuit_id=lawsuit_id,
        task_type_id=privada_id,
        user_ids=[str(colaborador.user_id)],
        scheduled_date=AMANHA.isoformat(),
        is_private=True,
    )
    publica = await _create_post(
        client,
        headers,
        lawsuit_id=lawsuit_id,
        task_type_id=publica_id,
        user_ids=[str(factory.gestor.user_id)],
        scheduled_date=AMANHA.isoformat(),
    )

    do_gestor = await _list_activities(client, headers)
    assert _ids(do_gestor) == [publica["id"]]
    assert do_gestor["total"] == 1

    # Para o envolvido ela está lá, inteira.
    do_dono = await _list_activities(client, headers_colaborador, view="all")
    assert privada["id"] in _ids(do_dono)

    exportado = await client.post(
        "/api/v1/posts/export", json={"format": "xlsx", "filters": {}}, headers=headers
    )
    assert exportado.status_code == 200
    assert privada["id"].encode() not in exportado.content


async def test_export_de_atividades_respeita_o_filtro_ativo(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Regra 7: o export é do filtro, não da página visível — e sai nos dois formatos."""
    headers = factory.headers
    lawsuit_id = await factory.create()
    dentro_id = await _create_task_type(client, headers)
    fora_id = await _create_task_type(client, headers)
    await _create_post(
        client,
        headers,
        lawsuit_id=lawsuit_id,
        task_type_id=dentro_id,
        user_ids=[str(factory.gestor.user_id)],
        scheduled_date=AMANHA.isoformat(),
    )
    await _create_post(
        client,
        headers,
        lawsuit_id=lawsuit_id,
        task_type_id=fora_id,
        user_ids=[str(factory.gestor.user_id)],
        scheduled_date=AMANHA.isoformat(),
    )

    planilha = await client.post(
        "/api/v1/posts/export",
        json={"format": "xlsx", "filters": {"task_type_id": dentro_id}},
        headers=headers,
    )
    assert planilha.status_code == 200
    assert planilha.headers["content-disposition"].endswith('filename="atividades.xlsx"')
    assert planilha.content[:2] == b"PK"  # xlsx é um zip

    pdf = await client.post(
        "/api/v1/posts/export", json={"format": "pdf", "filters": {}}, headers=headers
    )
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"


async def test_atividades_isoladas_entre_tenants(
    client: AsyncClient, factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 8: quem garante o recorte é o RLS — a aplicação não filtra tenant."""
    headers = factory.headers
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, headers)
    await _create_post(
        client,
        headers,
        lawsuit_id=lawsuit_id,
        task_type_id=task_type_id,
        user_ids=[str(factory.gestor.user_id)],
        scheduled_date=AMANHA.isoformat(),
    )

    outro_gestor = await make_user(role=UserRole.GESTOR)
    de_outro_tenant = await _list_activities(client, _auth_header(outro_gestor), view="all")
    assert de_outro_tenant["items"] == []
    assert de_outro_tenant["total"] == 0


async def test_atividades_dentro_do_orcamento_de_queries(
    client: AsyncClient, factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 9 e §11 do CLAUDE.md: 3 queries — autenticação, página (com o total por
    janela) e rótulos. Com DADOS, e não com a base vazia: é com duas tarefas e dois
    responsáveis que um N+1 apareceria."""
    headers = factory.headers
    colega = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    lawsuit_id = await factory.create()
    for _ in range(2):
        task_type_id = await _create_task_type(client, headers)
        await _create_post(
            client,
            headers,
            lawsuit_id=lawsuit_id,
            task_type_id=task_type_id,
            user_ids=[str(factory.gestor.user_id), str(colega.user_id)],
            scheduled_date=AMANHA.isoformat(),
        )

    async with query_budget(app, 3, label="listagem de atividades"):
        resposta = await client.get("/api/v1/posts", headers=headers)
    assert resposta.status_code == 200
    assert resposta.json()["total"] == 2
