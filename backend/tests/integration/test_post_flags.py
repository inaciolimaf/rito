from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import _auth_header
from tests.integration.test_lawsuits_listing import LawsuitFactory, _make_factory
from tests.integration.test_posts import _create_task_type

_NOW = datetime.now(UTC)
_YESTERDAY = (_NOW - timedelta(days=1)).isoformat()
_TOMORROW = (_NOW + timedelta(days=1)).isoformat()
_NEXT_WEEK = (_NOW.date() + timedelta(days=7)).isoformat()


@pytest.fixture
async def factory(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> LawsuitFactory:
    return await _make_factory(client, make_user, app_session_factory)


async def _setup_post(
    client: AsyncClient,
    factory: LawsuitFactory,
    assignees: list[str],
    **flags: object,
) -> str:
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, factory.headers, reward=8)
    response = await client.post(
        "/api/v1/posts",
        json={
            "lawsuit_id": lawsuit_id,
            "task_type_id": task_type_id,
            "user_ids": assignees,
            "scheduled_date": "2026-08-10",
            **flags,
        },
        headers=factory.headers,
    )
    assert response.status_code == 201, response.json()
    return str(response.json()["id"])


def _assignee(body: dict[str, object], user_id: str) -> dict[str, object]:
    items = body["assignees"]
    assert isinstance(items, list)
    return next(item for item in items if item["id"] == user_id)


async def test_conclusao_individual_nao_fecha_para_os_outros(
    client: AsyncClient, factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    outro = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    post_id = await _setup_post(client, factory, [str(factory.gestor.user_id), str(outro.user_id)])

    completed = await client.post(
        f"/api/v1/posts/{post_id}/complete", json={}, headers=factory.headers
    )
    assert completed.status_code == 200
    body = completed.json()
    # Regra 1: cada linha fecha independente — a do outro continua aberta.
    assert _assignee(body, str(factory.gestor.user_id))["completed_at"] is not None
    assert _assignee(body, str(outro.user_id))["completed_at"] is None
    # Regra 3: a tarefa como um todo só fecha quando TODOS concluem.
    assert body["all_completed"] is False

    # Regra 2: os pontos creditados são o reward_snapshot (8).
    assert _assignee(body, str(factory.gestor.user_id))["points_earned"] == 8

    await client.post(f"/api/v1/posts/{post_id}/complete", json={}, headers=_auth_header(outro))
    final = await client.get(f"/api/v1/posts/{post_id}", headers=factory.headers)
    assert final.json()["all_completed"] is True


async def test_retroativa_no_futuro_retorna_422(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    post_id = await _setup_post(client, factory, [str(factory.gestor.user_id)])
    response = await client.post(
        f"/api/v1/posts/{post_id}/complete",
        json={"completed_at": _TOMORROW},
        headers=factory.headers,
    )
    assert response.status_code == 422


async def test_retroativa_credita_na_competencia_informada(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    post_id = await _setup_post(client, factory, [str(factory.gestor.user_id)])
    completed = await client.post(
        f"/api/v1/posts/{post_id}/complete",
        json={"completed_at": _YESTERDAY},
        headers=factory.headers,
    )
    assert completed.status_code == 200
    line = _assignee(completed.json(), str(factory.gestor.user_id))
    # Regra 5: completed_at é a data informada (competência), não "agora".
    assert datetime.fromisoformat(str(line["completed_at"])) - datetime.fromisoformat(
        _YESTERDAY
    ) < timedelta(seconds=1)
    assert line["points_earned"] == 8


async def test_reabrir_zera_conclusao_e_pontos(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    post_id = await _setup_post(client, factory, [str(factory.gestor.user_id)])
    await client.post(f"/api/v1/posts/{post_id}/complete", json={}, headers=factory.headers)

    reopened = await client.post(
        f"/api/v1/posts/{post_id}/reopen", json={}, headers=factory.headers
    )
    assert reopened.status_code == 200
    # Regra 6: reabrir zera completed_at e points_earned daquele responsável.
    line = _assignee(reopened.json(), str(factory.gestor.user_id))
    assert line["completed_at"] is None
    assert line["points_earned"] is None
    assert reopened.json()["all_completed"] is False


async def test_nao_responsavel_nao_conclui(
    client: AsyncClient, factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    post_id = await _setup_post(client, factory, [str(factory.gestor.user_id)])
    terceiro = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    response = await client.post(
        f"/api/v1/posts/{post_id}/complete", json={}, headers=_auth_header(terceiro)
    )
    assert response.status_code == 403


async def test_administrador_conclui_por_outro_e_fica_registrado(
    client: AsyncClient, factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    responsavel = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    admin = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.ADMINISTRADOR)
    post_id = await _setup_post(client, factory, [str(responsavel.user_id)])

    # Regra 9: COLABORADOR não pode concluir pela linha de outro.
    colega = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    proibido = await client.post(
        f"/api/v1/posts/{post_id}/complete",
        json={"user_id": str(responsavel.user_id)},
        headers=_auth_header(colega),
    )
    assert proibido.status_code == 403

    # Regra 9: ADMINISTRADOR pode — e completed_by registra quem executou.
    permitido = await client.post(
        f"/api/v1/posts/{post_id}/complete",
        json={"user_id": str(responsavel.user_id)},
        headers=_auth_header(admin),
    )
    assert permitido.status_code == 200
    line = _assignee(permitido.json(), str(responsavel.user_id))
    assert line["completed_at"] is not None
    assert line["completed_by"] == str(admin.user_id)


async def test_privada_invisivel_para_nao_envolvido_inclusive_gestor(
    client: AsyncClient, factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    post_id = await _setup_post(client, factory, [str(factory.gestor.user_id)], is_private=True)
    dono = await client.get(f"/api/v1/posts/{post_id}", headers=factory.headers)
    lawsuit_id = dono.json()["lawsuit_id"]

    terceiro_gestor = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.GESTOR)
    headers_terceiro = _auth_header(terceiro_gestor)

    # Regra 8: nem GESTOR vê — 404 no acesso direto.
    direto = await client.get(f"/api/v1/posts/{post_id}", headers=headers_terceiro)
    assert direto.status_code == 404

    # Regra 8: na listagem do processo aparece como presença, sem conteúdo.
    listagem = await client.get(f"/api/v1/lawsuits/{lawsuit_id}/posts", headers=headers_terceiro)
    (privada,) = [item for item in listagem.json() if item["id"] == post_id]
    assert privada["redacted"] is True
    assert privada["task_type_name"] == "Tarefa privada"
    assert privada["assignees"] == []
    assert privada["comments"] is None

    # Para o envolvido, conteúdo completo.
    envolvido = await client.get(f"/api/v1/posts/{post_id}", headers=factory.headers)
    assert envolvido.status_code == 200
    assert envolvido.json()["redacted"] is False


async def test_futura_oculta_ate_a_data(client: AsyncClient, factory: LawsuitFactory) -> None:
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, factory.headers)
    for scheduled, is_future in (("2026-08-10", False), (_NEXT_WEEK, True)):
        await client.post(
            "/api/v1/posts",
            json={
                "lawsuit_id": lawsuit_id,
                "task_type_id": task_type_id,
                "user_ids": [str(factory.gestor.user_id)],
                "scheduled_date": scheduled,
                "is_future": is_future,
            },
            headers=factory.headers,
        )

    listagem = await client.get(f"/api/v1/lawsuits/{lawsuit_id}/posts", headers=factory.headers)
    # Regra 7: a futura (daqui a uma semana) fica oculta; a comum aparece.
    assert len(listagem.json()) == 1
    assert listagem.json()[0]["is_future"] is False


async def test_read_e_star_sao_por_usuario(
    client: AsyncClient, factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    outro = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    post_id = await _setup_post(client, factory, [str(factory.gestor.user_id), str(outro.user_id)])

    starred = await client.post(f"/api/v1/posts/{post_id}/star", json={}, headers=factory.headers)
    assert starred.status_code == 200
    # Regra 11: a estrela é da linha do usuário — a do outro continua apagada.
    assert _assignee(starred.json(), str(factory.gestor.user_id))["is_starred"] is True
    assert _assignee(starred.json(), str(outro.user_id))["is_starred"] is False

    lidar = await client.post(
        f"/api/v1/posts/{post_id}/read", json={"value": True}, headers=_auth_header(outro)
    )
    assert _assignee(lidar.json(), str(outro.user_id))["is_read"] is True
    assert _assignee(lidar.json(), str(factory.gestor.user_id))["is_read"] is False


async def test_flags_combinaveis_no_create_e_no_put(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    # Regra 10: importante e urgente são independentes e combináveis.
    post_id = await _setup_post(
        client, factory, [str(factory.gestor.user_id)], is_important=True, is_urgent=True
    )
    body = (await client.get(f"/api/v1/posts/{post_id}", headers=factory.headers)).json()
    assert body["is_important"] is True
    assert body["is_urgent"] is True

    updated = await client.put(
        f"/api/v1/posts/{post_id}/flags",
        json={
            "is_important": False,
            "is_urgent": True,
            "is_future": False,
            "is_private": False,
            "show_in_schedule": True,
        },
        headers=factory.headers,
    )
    assert updated.status_code == 200
    assert updated.json()["is_important"] is False
    assert updated.json()["is_urgent"] is True
    assert updated.json()["show_in_schedule"] is True
