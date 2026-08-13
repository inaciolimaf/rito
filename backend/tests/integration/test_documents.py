"""Documentos e nuvem (spec 063, §8) — pasta/documento por contato e processo, upload
múltiplo tolerante a falha parcial, cascata de exclusão, quota por plano, busca,
ordenação e isolamento por tenant."""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.tokens import create_access_token
from app.domain.account.models import AccountPlan
from app.domain.documents import quota
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser
from tests.integration.test_lawsuits import (
    _create_customer,
    _create_lawsuit,
    _create_lawsuit_type,
    _create_stage,
)


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


async def _customer_scope(client: AsyncClient, headers: dict[str, str]) -> tuple[str, str]:
    customer_id = await _create_customer(client, headers, f"Cliente {uuid.uuid4().hex[:8]}")
    return "CUSTOMER", customer_id


async def _upload(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    scope_type: str,
    scope_id: str,
    folder_id: str | None = None,
    files: list[tuple[str, bytes, str]],
) -> list[dict[str, Any]]:
    # Any: JSON de upload aninha `document` (outro objeto) — dict[str, object] não
    # permite o segundo nível de indexação que os testes abaixo precisam
    # (`results[0]["document"]["id"]`), e não há um schema tipado do lado do teste.
    data: dict[str, str] = {"scope_type": scope_type, "scope_id": scope_id}
    if folder_id is not None:
        data["folder_id"] = folder_id
    response = await client.post(
        "/api/v1/documents",
        data=data,
        files=[("files", item) for item in files],
        headers=headers,
    )
    assert response.status_code == 201, response.text
    result: list[dict[str, Any]] = response.json()
    return result


def _txt(content: str = "conteúdo") -> tuple[str, bytes, str]:
    return (f"{uuid.uuid4().hex[:8]}.txt", content.encode(), "text/plain")


async def test_upload_cria_documento_na_raiz_e_dentro_de_pasta(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    scope_type, scope_id = await _customer_scope(client, headers)

    root_results = await _upload(
        client, headers, scope_type=scope_type, scope_id=scope_id, files=[_txt()]
    )
    assert root_results[0]["status"] == "uploaded"
    assert root_results[0]["document"]["folder_id"] is None

    folder_response = await client.post(
        "/api/v1/document-folders",
        json={"scope_type": scope_type, "scope_id": scope_id, "name": "Contratos"},
        headers=headers,
    )
    assert folder_response.status_code == 201, folder_response.text
    folder_id = folder_response.json()["id"]

    nested_results = await _upload(
        client,
        headers,
        scope_type=scope_type,
        scope_id=scope_id,
        folder_id=folder_id,
        files=[_txt()],
    )
    assert nested_results[0]["document"]["folder_id"] == folder_id

    listing = await client.get(
        "/api/v1/documents",
        params={"scope_type": scope_type, "scope_id": scope_id},
        headers=headers,
    )
    assert listing.status_code == 200
    body = listing.json()
    assert len(body["documents"]) == 1
    assert len(body["folders"]) == 1


async def test_upload_multiplo_arquivo_invalido_nao_impede_os_outros(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    scope_type, scope_id = await _customer_scope(client, headers)

    results = await _upload(
        client,
        headers,
        scope_type=scope_type,
        scope_id=scope_id,
        files=[
            _txt("primeiro"),
            ("virus.exe", b"MZ", "application/x-msdownload"),
            _txt("terceiro"),
        ],
    )
    statuses = [item["status"] for item in results]
    assert statuses == ["uploaded", "error", "uploaded"]
    assert results[1]["error"] is not None


async def test_pasta_duplicada_no_mesmo_nivel_retorna_409(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    scope_type, scope_id = await _customer_scope(client, headers)

    payload = {"scope_type": scope_type, "scope_id": scope_id, "name": "Contratos"}
    first = await client.post("/api/v1/document-folders", json=payload, headers=headers)
    assert first.status_code == 201
    second = await client.post("/api/v1/document-folders", json=payload, headers=headers)
    assert second.status_code == 409


async def test_excluir_pasta_remove_subpasta_e_documento_em_cascata(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    scope_type, scope_id = await _customer_scope(client, headers)

    parent = await client.post(
        "/api/v1/document-folders",
        json={"scope_type": scope_type, "scope_id": scope_id, "name": "Pai"},
        headers=headers,
    )
    parent_id = parent.json()["id"]
    child = await client.post(
        "/api/v1/document-folders",
        json={
            "scope_type": scope_type,
            "scope_id": scope_id,
            "parent_folder_id": parent_id,
            "name": "Filha",
        },
        headers=headers,
    )
    child_id = child.json()["id"]
    upload_results = await _upload(
        client,
        headers,
        scope_type=scope_type,
        scope_id=scope_id,
        folder_id=child_id,
        files=[_txt()],
    )
    document_id = upload_results[0]["document"]["id"]

    delete_response = await client.delete(f"/api/v1/document-folders/{parent_id}", headers=headers)
    assert delete_response.status_code == 204

    child_gone = await client.get(
        "/api/v1/documents",
        params={"scope_type": scope_type, "scope_id": scope_id, "folder_id": parent_id},
        headers=headers,
    )
    assert child_gone.status_code == 404

    download = await client.get(f"/api/v1/documents/{document_id}/download", headers=headers)
    assert download.status_code == 404


async def test_quota_bloqueia_upload_acima_do_limite_do_plano(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Menor plano real é 50 GB (regra 6) — inviável alocar isso num teste. Em vez
    # disso, a quota do plano ESSENCIAL é reduzida a 0 só para este teste, o que faz
    # qualquer upload (mesmo de 1 byte) estourar (regra 5).
    monkeypatch.setitem(quota.PLAN_QUOTA_GB, AccountPlan.ESSENCIAL, 0)

    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    scope_type, scope_id = await _customer_scope(client, headers)

    results = await _upload(
        client,
        headers,
        scope_type=scope_type,
        scope_id=scope_id,
        files=[("pequeno.txt", b"conteudo", "text/plain")],
    )
    assert results[0]["status"] == "error"
    assert "quota" in (results[0]["error"] or "").lower()


async def test_quota_soma_todos_os_escopos_do_tenant(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    scope_type, scope_id = await _customer_scope(client, headers)

    before = (await client.get("/api/v1/account/storage", headers=headers)).json()
    await _upload(
        client, headers, scope_type=scope_type, scope_id=scope_id, files=[_txt("abc" * 100)]
    )
    after = (await client.get("/api/v1/account/storage", headers=headers)).json()
    assert after["used_bytes"] > before["used_bytes"]


async def test_download_gera_url_assinada(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    scope_type, scope_id = await _customer_scope(client, headers)

    results = await _upload(
        client, headers, scope_type=scope_type, scope_id=scope_id, files=[_txt()]
    )
    document_id = results[0]["document"]["id"]

    download = await client.get(f"/api/v1/documents/{document_id}/download", headers=headers)
    assert download.status_code == 200
    assert download.json()["url"].startswith("http")


async def test_busca_cobre_todas_as_pastas_do_escopo(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    scope_type, scope_id = await _customer_scope(client, headers)

    folder = await client.post(
        "/api/v1/document-folders",
        json={"scope_type": scope_type, "scope_id": scope_id, "name": "Sub"},
        headers=headers,
    )
    folder_id = folder.json()["id"]
    await _upload(
        client,
        headers,
        scope_type=scope_type,
        scope_id=scope_id,
        folder_id=folder_id,
        files=[("relatorio-financeiro.txt", b"x", "text/plain")],
    )

    search = await client.get(
        "/api/v1/documents/search",
        params={"scope_type": scope_type, "scope_id": scope_id, "q": "financeiro"},
        headers=headers,
    )
    assert search.status_code == 200
    assert len(search.json()["documents"]) == 1


async def test_ordenacao_por_nome_data_tamanho_tipo(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    scope_type, scope_id = await _customer_scope(client, headers)

    await _upload(
        client,
        headers,
        scope_type=scope_type,
        scope_id=scope_id,
        files=[("b.txt", b"12345", "text/plain"), ("a.txt", b"1", "text/plain")],
    )

    response = await client.get(
        "/api/v1/documents",
        params={
            "scope_type": scope_type,
            "scope_id": scope_id,
            "sort": "name",
            "order": "asc",
        },
        headers=headers,
    )
    names = [item["filename"] for item in response.json()["documents"]]
    assert names == ["a.txt", "b.txt"]

    by_size_desc = await client.get(
        "/api/v1/documents",
        params={
            "scope_type": scope_type,
            "scope_id": scope_id,
            "sort": "size_bytes",
            "order": "desc",
        },
        headers=headers,
    )
    sizes = [item["size_bytes"] for item in by_size_desc.json()["documents"]]
    assert sizes == sorted(sizes, reverse=True)


async def test_escopo_de_processo_funciona_e_escopo_de_outro_tenant_retorna_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    lawsuit_type_id, _group_id = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    lawsuit = await _create_lawsuit(
        client,
        headers,
        user_id=str(gestor.user_id),
        lawsuit_type_id=lawsuit_type_id,
        stage_id=stage_id,
    )
    lawsuit_id = str(lawsuit["id"])

    results = await _upload(
        client, headers, scope_type="LAWSUIT", scope_id=lawsuit_id, files=[_txt()]
    )
    assert results[0]["status"] == "uploaded"

    other_tenant = await make_user(role=UserRole.GESTOR)
    other_headers = _auth_header(other_tenant)
    forbidden = await client.get(
        "/api/v1/documents",
        params={"scope_type": "LAWSUIT", "scope_id": lawsuit_id},
        headers=other_headers,
    )
    assert forbidden.status_code == 404


async def test_tenant_a_nao_ve_documento_de_tenant_b(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor_a = await make_user(role=UserRole.GESTOR)
    headers_a = _auth_header(gestor_a)
    scope_type, scope_id = await _customer_scope(client, headers_a)
    await _upload(client, headers_a, scope_type=scope_type, scope_id=scope_id, files=[_txt()])

    gestor_b = await make_user(role=UserRole.GESTOR)
    headers_b = _auth_header(gestor_b)
    cross_tenant = await client.get(
        "/api/v1/documents",
        params={"scope_type": scope_type, "scope_id": scope_id},
        headers=headers_b,
    )
    assert cross_tenant.status_code == 404


async def test_troca_de_plano_por_gestor_reflete_na_quota(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)

    account_payload = {
        "name": "Escritório Teste",
        "alternate_name": "Teste",
        "identification": "11.222.333/0001-81",
        "country": "BRASIL",
        "state": "SP",
        "city": "São Paulo",
        "postal_code": "01310-100",
        "street": "Av. Paulista, 1000",
        "region": "Bela Vista",
        "cellphone": "11999998888",
        "phone": "1130004000",
        "email": "contato@escritorioteste.com.br",
        "email_admin": "financeiro@escritorioteste.com.br",
        "timezone": "America/Sao_Paulo",
    }
    create = await client.put("/api/v1/account", json=account_payload, headers=headers)
    assert create.status_code == 200, create.text
    assert create.json()["plan"] == "ESSENCIAL"

    updated = await client.put("/api/v1/account/plan", json={"plan": "ELITE"}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["plan"] == "ELITE"

    storage = await client.get("/api/v1/account/storage", headers=headers)
    assert storage.json()["quota_bytes"] == 100 * 1024**3
    assert storage.json()["plan"] == "ELITE"
