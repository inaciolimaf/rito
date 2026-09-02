"""Spec 035 — comentários, @menções, anexos e notificações in-app.

Cobre as regras 1 (menção persistida como id), 2 (menção sem acesso ignorada), 3
(janela de 15 min), 4 (exclusão soft preserva a thread), 5 (50 MB + allowlist),
6 (URL assinada de 5 min), 7 (anexo de tarefa privada), 9 (excluir comentário
remove anexos) e o isolamento de tenant nas três tabelas novas (CLAUDE.md §4).
"""

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.attachments.rules import MAX_ATTACHMENT_BYTES, AttachmentTooLargeError
from app.domain.attachments.service import AttachmentService
from app.domain.users.models import UserRole
from app.integrations.storage.s3 import create_file_storage
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import _auth_header
from tests.integration.test_lawsuits_listing import LawsuitFactory, _make_factory
from tests.integration.test_posts import _create_task_type


@pytest.fixture
async def factory(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> LawsuitFactory:
    return await _make_factory(client, make_user, app_session_factory)


async def _setup_post(
    client: AsyncClient, factory: LawsuitFactory, **flags: object
) -> dict[str, Any]:
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, factory.headers, reward=8)
    response = await client.post(
        "/api/v1/posts",
        json={
            "lawsuit_id": lawsuit_id,
            "task_type_id": task_type_id,
            "user_ids": [str(factory.gestor.user_id)],
            "scheduled_date": "2026-08-10",
            **flags,
        },
        headers=factory.headers,
    )
    assert response.status_code == 201, response.json()
    return dict(response.json())


async def _comment(
    client: AsyncClient, headers: dict[str, str], post_id: str, body: str
) -> dict[str, Any]:
    response = await client.post(
        f"/api/v1/posts/{post_id}/comments", json={"body": body}, headers=headers
    )
    assert response.status_code == 201, response.json()
    return dict(response.json())


async def _rename_user(
    sessions: async_sessionmaker[AsyncSession], tenant_id: object, user_id: object, name: str
) -> None:
    """O make_user nasce com o nome fixo "Usuário de Teste" — a menção por nome
    precisa de nomes distintos."""
    async with sessions() as session, session.begin():
        await set_tenant_context(session, tenant_id)  # type: ignore[arg-type]
        await session.execute(
            text("UPDATE users SET name = :name WHERE id = CAST(:id AS uuid)"),
            {"name": name, "id": str(user_id)},
        )


async def _upload(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    target_type: str,
    target_id: str,
    filename: str = "documento.pdf",
    content: bytes = b"%PDF-1.4 conteudo de teste",
    content_type: str = "application/pdf",
) -> Any:
    return await client.post(
        "/api/v1/attachments",
        files={"file": (filename, content, content_type)},
        data={"attached_to_type": target_type, "attached_to_id": target_id},
        headers=headers,
    )


@pytest.mark.commits
async def test_criar_comentario_e_listar_thread_em_ordem_crescente(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    post = await _setup_post(client, factory)
    primeiro = await _comment(client, factory.headers, str(post["id"]), "Primeiro contato")
    await _comment(client, factory.headers, str(post["id"]), "Cliente retornou")

    response = await client.get(f"/api/v1/posts/{post['id']}/comments", headers=factory.headers)
    assert response.status_code == 200
    page = response.json()
    assert page["total"] == 2
    # Regra 10: criação crescente — o primeiro criado vem primeiro.
    assert [item["body"] for item in page["items"]] == ["Primeiro contato", "Cliente retornou"]
    assert page["items"][0]["author"]["name"] == "Usuário de Teste"
    assert page["items"][0]["deleted"] is False
    assert page["next_cursor"] is None

    # Keyset: limit=1 devolve cursor e a próxima página continua de onde parou.
    first_page = await client.get(
        f"/api/v1/posts/{post['id']}/comments?limit=1", headers=factory.headers
    )
    cursor = first_page.json()["next_cursor"]
    assert cursor is not None
    second_page = await client.get(
        f"/api/v1/posts/{post['id']}/comments?limit=1&cursor={cursor}", headers=factory.headers
    )
    remaining = second_page.json()["items"]
    assert [item["body"] for item in remaining] == ["Cliente retornou"]
    assert remaining[0]["id"] != primeiro["id"]


async def test_mencao_gera_notificacao_in_app(
    client: AsyncClient,
    factory: LawsuitFactory,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    alvo = await make_user(tenant_id=factory.gestor.tenant_id)
    await _rename_user(app_session_factory, alvo.tenant_id, alvo.user_id, "Marina Costa")
    post = await _setup_post(client, factory)

    comment = await _comment(client, factory.headers, str(post["id"]), "@Marina Costa, vê isso")
    # Regra 1: a menção é resolvida na gravação e persistida como id.
    assert comment["mentioned_user_ids"] == [str(alvo.user_id)]

    # Regra 8: a notificação é in-app — aparece no sino da Marina.
    notifications = await client.get("/api/v1/notifications", headers=_auth_header(alvo))
    assert notifications.status_code == 200
    items = notifications.json()["items"]
    assert len(items) == 1
    assert items[0]["kind"] == "mention"
    assert "mencionou você" in items[0]["title"]
    assert items[0]["link"] == f"/posts/{post['id']}"
    assert items[0]["read_at"] is None

    unread = await client.get("/api/v1/notifications?unread=true", headers=_auth_header(alvo))
    assert unread.json()["total"] == 1

    # Marcar como lida (idempotente) e depois read-all.
    read = await client.post(
        f"/api/v1/notifications/{items[0]['id']}/read", headers=_auth_header(alvo)
    )
    assert read.status_code == 200
    assert read.json()["read_at"] is not None
    assert (
        await client.get("/api/v1/notifications?unread=true", headers=_auth_header(alvo))
    ).json()["total"] == 0

    read_all = await client.post("/api/v1/notifications/read-all", headers=_auth_header(alvo))
    assert read_all.status_code == 200

    # O autor não recebe notificação da própria menção…
    own = await client.get("/api/v1/notifications", headers=factory.headers)
    assert own.json()["total"] == 0
    # …e o autocomplete de menção encontra a Marina (qualquer colaborador consulta).
    mentionable = await client.get("/api/v1/users/mentionable?q=Marina", headers=factory.headers)
    assert mentionable.status_code == 200
    assert [item["id"] for item in mentionable.json()] == [str(alvo.user_id)]


async def test_mencao_a_quem_nao_tem_acesso_e_ignorada(
    client: AsyncClient,
    factory: LawsuitFactory,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Tarefa PRIVADA do gestor: o colega não é criador nem responsável — não tem acesso.
    outsider = await make_user(tenant_id=factory.gestor.tenant_id)
    await _rename_user(app_session_factory, outsider.tenant_id, outsider.user_id, "Fulano Fora")
    post = await _setup_post(client, factory, is_private=True)

    comment = await _comment(client, factory.headers, str(post["id"]), "cc @Fulano Fora")
    # Regra 2: ignorada silenciosamente — nem registra, nem notifica.
    assert comment["mentioned_user_ids"] == []
    notifications = await client.get("/api/v1/notifications", headers=_auth_header(outsider))
    assert notifications.json()["total"] == 0

    # E o outsider nem comenta na tarefa privada (404, não 403).
    denied = await client.post(
        f"/api/v1/posts/{post['id']}/comments",
        json={"body": "tentativa"},
        headers=_auth_header(outsider),
    )
    assert denied.status_code == 404


async def test_mencao_sobrevive_a_renomeacao_do_usuario(
    client: AsyncClient,
    factory: LawsuitFactory,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    alvo = await make_user(tenant_id=factory.gestor.tenant_id)
    await _rename_user(app_session_factory, alvo.tenant_id, alvo.user_id, "Nome Antigo")
    post = await _setup_post(client, factory)
    comment = await _comment(client, factory.headers, str(post["id"]), "oi @Nome Antigo")
    assert comment["mentioned_user_ids"] == [str(alvo.user_id)]

    await _rename_user(app_session_factory, alvo.tenant_id, alvo.user_id, "Nome Novissimo")

    # Regra 1: o que ficou gravado é o ID — renomear não quebra o link.
    response = await client.get(f"/api/v1/posts/{post['id']}/comments", headers=factory.headers)
    assert response.json()["items"][0]["mentioned_user_ids"] == [str(alvo.user_id)]


async def test_edicao_apos_15_minutos_so_administrador(
    client: AsyncClient,
    factory: LawsuitFactory,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    autor = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    post = await _setup_post(client, factory)
    # O gestor é responsável; o autor (colaborador) comenta — tarefa pública, acesso ok.
    comment = await _comment(client, _auth_header(autor), str(post["id"]), "versão 1")

    # 20 minutos no passado: fora da janela da regra 3.
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, factory.gestor.tenant_id)
        await session.execute(
            text(
                "UPDATE post_comments SET created_at = now() - interval '20 minutes' "
                "WHERE id = CAST(:id AS uuid)"
            ),
            {"id": comment["id"]},
        )

    late = await client.put(
        f"/api/v1/comments/{comment['id']}",
        json={"body": "versão 2"},
        headers=_auth_header(autor),
    )
    assert late.status_code == 403

    # ADMINISTRADOR+ edita a qualquer momento.
    admin_edit = await client.put(
        f"/api/v1/comments/{comment['id']}",
        json={"body": "versão 2 pelo gestor"},
        headers=factory.headers,
    )
    assert admin_edit.status_code == 200, admin_edit.json()
    assert admin_edit.json()["body"] == "versão 2 pelo gestor"

    # Dentro da janela, o autor edita o seu.
    recent = await _comment(client, _auth_header(autor), str(post["id"]), "no prazo")
    own_edit = await client.put(
        f"/api/v1/comments/{recent['id']}",
        json={"body": "no prazo, editado"},
        headers=_auth_header(autor),
    )
    assert own_edit.status_code == 200


@pytest.mark.commits
async def test_exclusao_soft_preserva_a_thread(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    post = await _setup_post(client, factory)
    primeiro = await _comment(client, factory.headers, str(post["id"]), "some")
    await _comment(client, factory.headers, str(post["id"]), "fica")

    deleted = await client.delete(f"/api/v1/comments/{primeiro['id']}", headers=factory.headers)
    assert deleted.status_code == 204

    # Regra 4: a thread se preserva — o removido aparece mascarado no lugar dele.
    response = await client.get(f"/api/v1/posts/{post['id']}/comments", headers=factory.headers)
    items = response.json()["items"]
    assert len(items) == 2
    assert items[0]["deleted"] is True
    assert items[0]["body"] is None
    assert items[1]["body"] == "fica"

    # Removido não edita nem remove de novo (404).
    assert (
        await client.put(
            f"/api/v1/comments/{primeiro['id']}", json={"body": "x"}, headers=factory.headers
        )
    ).status_code == 404


async def test_upload_acima_de_50mb_retorna_422(
    factory: LawsuitFactory,
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # Regra 5 no service (a validação é por len(content) — via HTTP seriam 50 MB de
    # payload no teste; o caminho HTTP do 422 está coberto no teste de tipo bloqueado).
    from app.domain.users.models import User

    post_id = uuid4()
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, factory.gestor.tenant_id)
        uploader = await session.get(User, factory.gestor.user_id)
        assert uploader is not None
        service = AttachmentService(
            session=session, storage=create_file_storage(), tenant_id=factory.gestor.tenant_id
        )
        with pytest.raises(AttachmentTooLargeError):
            await service.upload(
                uploader,
                attached_to_type="post",
                attached_to_id=post_id,
                filename="grande.pdf",
                content_type="application/pdf",
                content=b"x" * (MAX_ATTACHMENT_BYTES + 1),
            )


async def test_tipo_bloqueado_retorna_422_e_fluxo_completo_do_anexo(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    post = await _setup_post(client, factory)

    # Regra 5: executável bloqueado mesmo com content-type disfarçado.
    blocked = await _upload(
        client,
        factory.headers,
        target_type="post",
        target_id=str(post["id"]),
        filename="virus.exe",
        content_type="application/pdf",
    )
    assert blocked.status_code == 422

    # Upload válido na tarefa.
    uploaded = await _upload(client, factory.headers, target_type="post", target_id=str(post["id"]))
    assert uploaded.status_code == 201, uploaded.json()
    attachment = uploaded.json()
    assert attachment["filename"] == "documento.pdf"
    assert attachment["size_bytes"] > 0

    # Regra 6: a URL de download é assinada com validade de 5 minutos.
    download = await client.get(
        f"/api/v1/attachments/{attachment['id']}/download", headers=factory.headers
    )
    assert download.status_code == 200
    assert "X-Amz-Expires=300" in download.json()["url"]

    # Anexo em comentário aparece na thread…
    comment = await _comment(client, factory.headers, str(post["id"]), "segue anexo")
    on_comment = await _upload(
        client, factory.headers, target_type="comment", target_id=str(comment["id"])
    )
    assert on_comment.status_code == 201
    thread = await client.get(f"/api/v1/posts/{post['id']}/comments", headers=factory.headers)
    assert len(thread.json()["items"][0]["attachments"]) == 1

    # …e regra 9: excluir o comentário remove os anexos dele.
    await client.delete(f"/api/v1/comments/{comment['id']}", headers=factory.headers)
    gone = await client.get(
        f"/api/v1/attachments/{on_comment.json()['id']}/download", headers=factory.headers
    )
    assert gone.status_code == 404

    # Remover anexo manualmente: só quem enviou (ou ADMIN+) — e some de vez.
    removed = await client.delete(
        f"/api/v1/attachments/{attachment['id']}", headers=factory.headers
    )
    assert removed.status_code == 204
    assert (
        await client.get(
            f"/api/v1/attachments/{attachment['id']}/download", headers=factory.headers
        )
    ).status_code == 404


async def test_anexo_de_tarefa_privada_respeita_visibilidade(
    client: AsyncClient,
    factory: LawsuitFactory,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    outsider = await make_user(tenant_id=factory.gestor.tenant_id)
    post = await _setup_post(client, factory, is_private=True)
    uploaded = await _upload(client, factory.headers, target_type="post", target_id=str(post["id"]))
    assert uploaded.status_code == 201

    # Regra 7: para o outsider o anexo e o upload simplesmente não existem (404).
    denied_upload = await _upload(
        client, _auth_header(outsider), target_type="post", target_id=str(post["id"])
    )
    assert denied_upload.status_code == 404
    denied_download = await client.get(
        f"/api/v1/attachments/{uploaded.json()['id']}/download", headers=_auth_header(outsider)
    )
    assert denied_download.status_code == 404


async def test_tenant_b_nao_enxerga_comentarios_anexos_nem_notificacoes(
    client: AsyncClient,
    factory: LawsuitFactory,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    alvo = await make_user(tenant_id=factory.gestor.tenant_id)
    await _rename_user(app_session_factory, alvo.tenant_id, alvo.user_id, "Marina RLS")
    post = await _setup_post(client, factory)
    comment = await _comment(client, factory.headers, str(post["id"]), "oi @Marina RLS")
    uploaded = await _upload(client, factory.headers, target_type="post", target_id=str(post["id"]))
    assert uploaded.status_code == 201

    intruder = await make_user()
    # Via API: 404 nos três recursos para o outro tenant.
    assert (
        await client.get(f"/api/v1/posts/{post['id']}/comments", headers=_auth_header(intruder))
    ).status_code == 404
    assert (
        await client.get(
            f"/api/v1/attachments/{uploaded.json()['id']}/download",
            headers=_auth_header(intruder),
        )
    ).status_code == 404
    assert (await client.get("/api/v1/notifications", headers=_auth_header(intruder))).json()[
        "total"
    ] == 0

    # Direto no banco: RLS filtra as três tabelas pelo app.tenant_id da sessão —
    # o dono enxerga 1 linha, o intruso 0 (os dois sentidos, senão o 0 seria trivial).
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, factory.gestor.tenant_id)
        rows = await session.execute(
            text("SELECT id FROM notifications WHERE user_id = CAST(:id AS uuid)"),
            {"id": str(alvo.user_id)},
        )
        notification_id = str(rows.scalar_one())
    for table, row_id in [
        ("post_comments", comment["id"]),
        ("attachments", uploaded.json()["id"]),
        ("notifications", notification_id),
    ]:
        for tenant, expected in ((intruder.tenant_id, 0), (factory.gestor.tenant_id, 1)):
            async with app_session_factory() as session, session.begin():
                await set_tenant_context(session, tenant)
                rows = await session.execute(
                    text(f"SELECT count(*) FROM {table} WHERE id = CAST(:id AS uuid)"),
                    {"id": row_id},
                )
                assert rows.scalar_one() == expected, (table, tenant)
